"""A small read-only review window over application conversion and publication."""

from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLineEdit,
    QHeaderView, QLabel, QMainWindow, QPushButton, QScrollArea, QSplitter, QTabWidget, QTextBrowser, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from pdf_to_ofx.application.convert import (
    ConversionResult, ExportReadiness, ExportStatus, StatementAnalysis,
    analyze_pdf, assess_export_readiness, export_analysis,
)
from pdf_to_ofx.application.export import write_ofx, write_csv
from pdf_to_ofx.application.csv_export import assess_csv_readiness, export_csv_analysis
from pdf_to_ofx.ofx.generator import OFXProfile
from pdf_to_ofx.application.review import ReviewSession
from pdf_to_ofx.ui.presentation import diagnostic_text, DIRECTIONS, movement_totals, export_issue_text
from pdf_to_ofx.ui.worker import AnalysisWorker
from pdf_to_ofx.domain.errors import (
    OFXGenerationError, PDFExtractionError, StatementParseError,
    StatementValidationError, UnsupportedLayoutError,
)
from pdf_to_ofx.domain.evidence import AnalysisStatus, EvidenceStatus


def format_money(value: Decimal | None, currency_code: str | None = "BRL") -> str:
    """Brazilian display only; domain values and OFX bytes remain untouched."""
    if value is None:
        return "Não informado pelo extrato"
    formatted = format(value if value != 0 else Decimal("0"), ",.2f")
    prefix = "R$ " if currency_code == "BRL" else (currency_code + " " if currency_code else "")
    return prefix + formatted.translate(str.maketrans(",.", ".,"))


def conversion_error_message(error: Exception) -> str:
    # Never interpolate exception text: library failures can contain PDF data.
    matches = lambda kind: issubclass(error, kind) if isinstance(error, type) else isinstance(error, kind)
    if matches(PDFExtractionError):
        return ("Não foi possível extrair texto do PDF. Use um PDF com texto selecionável "
                "e verifique se o arquivo está danificado ou protegido. PDFs digitalizados "
                "não são suportados.")
    if matches(UnsupportedLayoutError):
        return "O formato deste extrato ainda não é suportado."
    if matches(StatementParseError):
        return "O extrato está incompleto ou não segue o formato suportado. O OFX não foi gerado."
    if matches(StatementValidationError):
        return "Os valores ou saldos do extrato não passaram na validação. O OFX não foi gerado."
    if matches(OFXGenerationError):
        return ("Não foi possível gerar o OFX. Os dados bancários ou identificadores "
                "necessários estão ausentes, inválidos ou inconsistentes.")
    return "Não foi possível processar este PDF com segurança. Verifique o arquivo e tente novamente."


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.selected_file: Path | None = None
        self.conversion_result: ConversionResult | None = None
        self.analysis: StatementAnalysis | None = None
        self.export_readiness: ExportReadiness | None = None
        self.export_metadata: OFXProfile | None = None
        self.review_session = None
        self._request_id = 0
        self._worker = None
        self._pending = None
        self._closing = False
        self.setWindowTitle("ExtratoLab")
        self.resize(1180, 820)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        # Keep controls reachable at smaller desktop resolutions and scaled DPI.
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.content_scroll.setWidget(central)
        self.setCentralWidget(self.content_scroll)

        title = QLabel("ExtratoLab  /  Conferência financeira")
        title.setObjectName("brand")
        font = title.font()
        font.setPointSize(font.pointSize() + 6)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)
        privacy = QLabel("Processamento realizado localmente. Nenhum extrato é enviado pela internet.")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)

        actions = QHBoxLayout()
        self.select_button = QPushButton("Abrir PDF")
        self.select_button.clicked.connect(self.select_pdf)
        actions.addWidget(self.select_button)
        actions.addWidget(QLabel("ou arraste um único PDF para esta janela"))
        actions.addStretch()
        self.save_button = QPushButton("Salvar OFX")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_ofx)
        actions.addWidget(self.save_button)
        self.csv_button = QPushButton("Salvar CSV")
        self.csv_button.setEnabled(False)
        self.csv_button.clicked.connect(self.save_csv)
        actions.addWidget(self.csv_button)
        layout.addLayout(actions)

        self.metadata_group = QGroupBox("Dados bancários")
        form = QFormLayout(self.metadata_group)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.metadata_fields = {}
        for key, caption in (("organization", "Instituição (ORG)"), ("institution_id", "Identificador (FID)"),
                             ("bank_id", "Banco (BANKID)"), ("branch_id", "Agência (BRANCHID)"),
                             ("account_id", "Conta (ACCTID)")):
            field = QLineEdit()
            field.setMinimumHeight(30)
            field.setAccessibleName(caption)
            field.textChanged.connect(self._metadata_changed)
            self.metadata_fields[key] = field
            form.addRow(caption, field)
        self.account_type = QComboBox()
        self.account_type.setMinimumHeight(30)
        self.account_type.addItems(["CHECKING", "SAVINGS"])
        self.account_type.currentTextChanged.connect(self._metadata_changed)
        form.addRow("Tipo de conta", self.account_type)
        self.metadata_group.hide()
        # Export form is placed in its contextual tab below.

        self.file_label = QLabel("Nenhum PDF selecionado.")
        self.file_label.setTextFormat(Qt.TextFormat.PlainText)
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)
        self.analysis_status_label = QLabel("Análise: aguardando documento")
        self.analysis_status_label.setAccessibleName("Estado da interpretação")
        self.analysis_status_label.setWordWrap(True)
        layout.addWidget(self.analysis_status_label)

        summary = QGroupBox("Resumo financeiro")
        grid = QGridLayout(summary)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(8)
        self.summary_labels: dict[str, QLabel] = {}
        fields = (
            ("bank", "Instituição"), ("period", "Período"),
            ("count", "Lançamentos"), ("credits", "Créditos"),
            ("debits", "Débitos"), ("opening", "Saldo inicial"),
            ("closing", "Saldo final"), ("validation", "Validação"),
        )
        for index, (key, caption) in enumerate(fields):
            label = QLabel("—")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            if key == "bank":
                label.setMinimumHeight(40)
            self.summary_labels[key] = label
            row, column = index // 2, (index % 2) * 2
            grid.addWidget(QLabel(caption + ":"), row, column)
            grid.addWidget(label, row, column + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        layout.addWidget(summary)

        layout.addWidget(QLabel("Lançamentos · somente leitura"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Data", "Descrição", "Tipo", "Valor", "Saldo após lançamento"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setMinimumHeight(240)
        splitter.addWidget(self.table)
        self.tabs = QTabWidget()
        self.details = QTextBrowser()
        self.details.setAccessibleName("Evidências do lançamento")
        self.details.setPlainText("Selecione uma movimentação para conferir os campos e a origem no PDF.")
        self.diagnostics = QTextBrowser()
        self.diagnostics.setAccessibleName("Verificações financeiras e diagnóstico")
        self.diagnostics.setPlainText("As verificações aparecerão após a análise.")
        self.tabs.addTab(self.details, "Conferência")
        self.tabs.addTab(self.diagnostics, "Diagnóstico")
        export_panel = QWidget()
        export_layout = QVBoxLayout(export_panel)
        export_note = QLabel("OFX exige dados bancários, moeda resolvida e saldo final. CSV exporta a interpretação aprovada sem dados bancários; campos ausentes ficam vazios. Os metadados valem apenas nesta sessão.")
        export_note.setWordWrap(True)
        export_layout.addWidget(export_note)
        self.export_status_label = QLabel("A prontidão de cada formato aparecerá após a análise.")
        self.export_status_label.setWordWrap(True)
        self.export_status_label.setAccessibleName("Prontidão OFX e CSV")
        export_layout.addWidget(self.export_status_label)
        export_layout.addWidget(self.metadata_group)
        export_layout.addStretch()
        export_scroll = QScrollArea()
        export_scroll.setWidgetResizable(True)
        export_scroll.setWidget(export_panel)
        self.tabs.addTab(export_scroll, "Exportação")
        splitter.addWidget(self.tabs)
        splitter.setSizes([740, 380])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, stretch=1)
        self.table.itemSelectionChanged.connect(self._show_selection)
        self.currency_label = QLabel("Moeda: —")
        self.totals_label = QLabel("Totais: —")
        layout.insertWidget(layout.indexOf(summary) + 1, self.currency_label)
        layout.insertWidget(layout.indexOf(summary) + 2, self.totals_label)

        self.status_label = QLabel("Selecione um PDF para começar.")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName("Status da análise")
        layout.addWidget(self.status_label)
        self.setStyleSheet("""
            QMainWindow { background: #f3f6f8; }
            QWidget { color: #203648; font-size: 13px; }
            QLabel#brand { color: #123f48; font-size: 25px; font-weight: 700; }
            QGroupBox { background: white; border: 1px solid #cad7df; border-radius: 8px;
                        margin-top: 14px; padding: 12px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QPushButton { background: #126d70; color: white; border: 1px solid #126d70;
                          border-radius: 6px; padding: 10px 16px; font-weight: 600; }
            QPushButton:hover { background: #0d5558; }
            QPushButton:disabled { background: #d9e1e6; color: #596c78; border-color: #d9e1e6; }
            QPushButton:focus, QLineEdit:focus, QComboBox:focus { border: 2px solid #007b83; }
            QLineEdit, QComboBox { background: white; border: 1px solid #a9bbc7; padding: 5px; border-radius: 4px; }
            QTableWidget, QTextBrowser { background: white; border: 1px solid #cad7df;
                                        selection-background-color: #d7edee; selection-color: #123f48; }
            QTableWidget { alternate-background-color: #f3f7f9; gridline-color: #e2e9ed; }
            QHeaderView::section { background: #e8eff3; padding: 9px; border: none; font-weight: 600; }
            QTabWidget::pane { border: 1px solid #cad7df; background: white; }
            QTabBar::tab { background: #e4ecef; padding: 10px; }
            QTabBar::tab:selected { background: white; color: #125f63; font-weight: 600; }
        """)

    def _clear_result(self) -> None:
        # Clear memory AND visible fields before every attempt, including invalid
        # paths. A failed second conversion cannot export the previous OFX.
        self.review_session = None
        self.details.setPlainText("Selecione uma movimentação para conferir os campos e a origem no PDF.")
        self.diagnostics.setPlainText("As verificações aparecerão após a análise.")
        self.currency_label.setText("Moeda: —")
        self.totals_label.setText("Totais: —")
        self.selected_file = None
        self.conversion_result = None
        self.analysis = None
        self.export_readiness = None
        self.export_metadata = None
        self.analysis_status_label.setText("Análise: aguardando documento")
        self.export_status_label.setText("A prontidão de cada formato aparecerá após a análise.")
        for field in self.metadata_fields.values():
            field.blockSignals(True)
            field.clear()
            field.blockSignals(False)
        self.account_type.blockSignals(True)
        self.account_type.setCurrentIndex(0)
        self.account_type.blockSignals(False)
        self.metadata_group.hide()
        self.save_button.setEnabled(False)
        self.csv_button.setEnabled(False)
        self.file_label.setText("Nenhum PDF selecionado.")
        self.table.clearContents()
        self.table.setRowCount(0)
        for label in self.summary_labels.values():
            label.setText("—")

    def _error(self, message: str) -> None:
        self.status_label.setText("Erro: " + message)
        if self.analysis is None:
            self.analysis_status_label.setText("Análise: não concluída")

    def select_pdf(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Selecionar extrato PDF", "", "Arquivos PDF (*.pdf)")
        if filename:
            self.load_pdf(Path(filename), background=True)

    def load_pdf(self, path: Path, *, background: bool = False) -> None:
        """Interactive callers use a worker; synchronous mode supports scripts/tests."""
        self._pending = None
        self._request_id += 1
        request_id = self._request_id
        self._clear_result()
        if path.suffix.lower() != ".pdf" or not path.is_file():
            self._pending = None
            self._error("Selecione um arquivo existente com extensão .pdf.")
            return
        self.file_label.setText(path.name + " · analisando")
        self.status_label.setText("Processando PDF localmente…")
        self.analysis_status_label.setText("Análise: em andamento")
        if background:
            if self._worker is not None:
                self._pending = (request_id, path)
            else:
                self._start_worker(request_id, path)
            return
        self.select_button.setEnabled(False)
        try:
            self._accept_analysis(request_id, path, analyze_pdf(path), None)
        except Exception as error:
            self._accept_analysis(request_id, path, None, type(error))
        finally:
            self.select_button.setEnabled(True)

    def _start_worker(self, request_id, path):
        worker = AnalysisWorker(request_id, path, analyze_pdf, self)
        self._worker = worker
        worker.completed.connect(self._worker_completed, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._worker_finished, Qt.ConnectionType.QueuedConnection)
        worker.start()

    @Slot(int, object, object)
    def _worker_completed(self, number, result, error):
        worker = self.sender()
        self._accept_analysis(number, worker.path, result, error)

    @Slot()
    def _worker_finished(self):
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if self._closing:
            self.close()
        elif self._pending is not None:
            number, path = self._pending
            self._pending = None
            self._start_worker(number, path)

    def _accept_analysis(self, request_id, path, analysis, error_type):
        if request_id != self._request_id or self._closing:
            return
        if error_type is not None:
            self._clear_result()
            self._error(conversion_error_message(error_type))
            return
        self.analysis = analysis
        self.file_label.setText(path.name)
        labels = {AnalysisStatus.SUCCESS: "SUCCESS · interpretação aprovada",
                  AnalysisStatus.AMBIGUOUS: "AMBIGUOUS · interpretação ambígua",
                  AnalysisStatus.UNSUPPORTED: "UNSUPPORTED · capacidade estrutural ausente",
                  AnalysisStatus.INVALID: "INVALID · inconsistência identificada"}
        self.analysis_status_label.setText("Análise: " + labels[analysis.status])
        self.diagnostics.setPlainText(diagnostic_text(analysis))
        if analysis.status != AnalysisStatus.SUCCESS:
            self.export_status_label.setText("OFX e CSV bloqueados: a interpretação não foi aprovada.")
            self._error(diagnostic_text(analysis).splitlines()[0])
            self.tabs.setCurrentIndex(1)
            return
        self.csv_button.setEnabled(assess_csv_readiness(analysis).status == ExportStatus.READY_TO_EXPORT)
        self._show_result(analysis)
        self.selected_file = path
        self.review_session = ReviewSession(analysis)
        self.tabs.setCurrentIndex(0)
        self._refresh_export()

    def closeEvent(self, event):
        if self._worker is not None:
            self._closing = True
            self._request_id += 1
            self._pending = None
            self.select_button.setEnabled(False)
            self.status_label.setText("Encerrando após o processamento local em andamento…")
            event.ignore()
        else:
            self._clear_result()
            event.accept()

    def _show_selection(self):
        row = self.table.currentRow()
        if (self.analysis is None or self.analysis.statement is None or self.review_session is None
                or row < 0 or not self.table.selectedItems()):
            self.details.setPlainText("Selecione uma movimentação para conferir os campos e a origem no PDF.")
            return
        transaction = self.analysis.statement.transactions[row]
        currency = self.analysis.statement.currency
        lines = [transaction.posting_date.isoformat(), transaction.description,
                 ("Crédito" if transaction.amount >= 0 else "Débito") + ": " + format_money(transaction.amount, currency.code if currency else None),
                 "Saldo após: " + format_money(transaction.balance_after, currency.code if currency else None)]
        source = self.review_session.transaction_source(row)
        if source is None:
            lines.append("Referências de origem indisponíveis.")
        else:
            lines.append("Base da direção: " + DIRECTIONS.get(source.direction_basis, "Base estrutural registrada pelo motor (consulte os tokens abaixo)."))
            for label, spans in (("Data", (source.date_source,)), ("Descrição", source.description_sources),
                                 ("Valor", (source.amount_source,)), ("Direção", (source.direction_source,)),
                                 ("Saldo", (source.balance_source,))):
                lines.append("\n" + label)
                for span in spans or (None,):
                    if span is None:
                        lines.append("Evidência individual não disponível.")
                        continue
                    resolved = self.review_session.resolve(span)
                    basis = "linha de texto" if span.basis == "text_line" else "linha visual"
                    lines.append(f"Página {span.page} · {basis} {span.row} · tokens {span.word_start}:{span.word_end}")
                    if resolved.tokens is None:
                        lines.append("Referência registrada; tokens indisponíveis nesta sessão.")
                    else:
                        lines.append(" ".join(resolved.tokens))
        self.details.setPlainText("\n".join(lines))

    def _metadata_changed(self, *_args) -> None:
        if self.analysis is None or self.analysis.status != AnalysisStatus.SUCCESS:
            return
        self.export_metadata = OFXProfile(
            **{key: field.text().strip() for key, field in self.metadata_fields.items()},
            account_type=self.account_type.currentText(),
        )
        self._refresh_export()

    def _refresh_export(self) -> None:
        self.conversion_result = None
        self.save_button.setEnabled(False)
        if self.analysis is None:
            return
        self.export_readiness = assess_export_readiness(self.analysis, self.export_metadata)
        status = self.export_readiness.status
        csv_ready = assess_csv_readiness(self.analysis).status == ExportStatus.READY_TO_EXPORT
        csv_text = "CSV pronto para salvar." if csv_ready else "CSV bloqueado pela validação da interpretação."
        ofx_text = "OFX pronto para salvar." if status == ExportStatus.READY_TO_EXPORT else export_issue_text(self.export_readiness.issues)
        self.export_status_label.setText(csv_text + "\n" + ofx_text)
        if status == ExportStatus.EXPORT_METADATA_REQUIRED:
            self.metadata_group.show()
            self.status_label.setText("Extrato interpretado. São necessários dados bancários adicionais para gerar o OFX.")
        elif status != ExportStatus.READY_TO_EXPORT:
            self.status_label.setText("Extrato interpretado. " + ofx_text)
        else:
            try:
                ofx = export_analysis(self.analysis, self.export_metadata)
            except OFXGenerationError:
                self.export_readiness = ExportReadiness(ExportStatus.EXPORT_REQUIREMENTS_MISSING, ("generation_failed",))
                self.export_status_label.setText(csv_text + "\n" + export_issue_text(self.export_readiness.issues))
                self._error("Extrato interpretado, mas não foi possível gerar o OFX com segurança.")
                return
            self.conversion_result = ConversionResult(self.analysis.bank_name, self.analysis.statement, ofx)
            self.save_button.setEnabled(True)
            self.status_label.setText("Conversão pronta. Revise os lançamentos e escolha Salvar OFX.")

    def _show_result(self, result: StatementAnalysis) -> None:
        statement = result.statement
        assert statement is not None
        evidence = result.evidence
        validation = ("Abertura e fechamento reconciliados" if evidence.opening_closing_reconciled == EvidenceStatus.VERIFIED
                      else "Saldos progressivos verificados; abertura não reconciliada" if evidence.running_balance_verified == EvidenceStatus.VERIFIED
                      else "Pontos de controle verificados" if evidence.checkpoints_verified == EvidenceStatus.VERIFIED
                      else "Subtotais verificados" if evidence.group_subtotals_verified == EvidenceStatus.VERIFIED
                      else "Totais de créditos e débitos verificados" if evidence.credit_total_verified == evidence.debit_total_verified == EvidenceStatus.VERIFIED
                      else "Verificação financeira não disponível")
        code = statement.currency.code if statement.currency else None
        self.currency_label.setText("Moeda: " + (code or "Não resolvida pelo documento"))
        credits, debits = movement_totals(statement.transactions)
        self.totals_label.setText("Créditos: " + format_money(credits, code) + "    /    Débitos: " + format_money(debits, code))
        if evidence.group_subtotals_verified == EvidenceStatus.VERIFIED:
            validation += "; subtotais verificados"
        values = {
            "bank": result.bank_name,
            "period": f"{statement.period_start:%d/%m/%Y} a {statement.period_end:%d/%m/%Y}",
            "count": str(len(statement.transactions)),
            "credits": str(sum(t.amount > 0 for t in statement.transactions)),
            "debits": str(sum(t.amount < 0 for t in statement.transactions)),
            "opening": format_money(statement.opening_balance, code),
            "closing": format_money(statement.closing_balance, code),
            "validation": validation,
        }
        for key, value in values.items():
            self.summary_labels[key].setText(value)
        self.table.setRowCount(len(statement.transactions))
        for row, transaction in enumerate(statement.transactions):
            cells = (
                transaction.posting_date.strftime("%d/%m/%Y"), transaction.description,
                "Crédito" if transaction.amount >= 0 else "Débito",
                format_money(transaction.amount, code), format_money(transaction.balance_after, code),
            )
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                item.setToolTip(text)
                if column >= 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.resizeRowsToContents()

    def save_ofx(self) -> None:
        # Guard the action itself, rather than relying only on the button state.
        if (self.conversion_result is None or self.selected_file is None
                or self.analysis is None or self.analysis.status != AnalysisStatus.SUCCESS
                or self.export_readiness is None
                or self.export_readiness.status != ExportStatus.READY_TO_EXPORT):
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, "Salvar OFX · escolha um nome novo", str(self.selected_file.with_suffix(".ofx")),
            "Arquivos OFX (*.ofx)", options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not filename:
            return
        output = Path(filename)
        if not output.suffix:
            output = output.with_suffix(".ofx")
        if output.suffix.lower() != ".ofx":
            self._error("Escolha um nome de arquivo com extensão .ofx.")
            return
        try:
            write_ofx(output, self.conversion_result.ofx)
        except FileExistsError:
            self._error("O arquivo de destino já existe. Escolha outro nome; nenhum arquivo foi substituído.")
        except Exception:
            self._error("Não foi possível salvar o OFX. Verifique a pasta e as permissões e tente novamente.")
        else:
            self.status_label.setText("OFX salvo com sucesso.")

    def save_csv(self) -> None:
        if (self.analysis is None or self.selected_file is None
                or assess_csv_readiness(self.analysis).status != ExportStatus.READY_TO_EXPORT):
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Salvar CSV · escolha um nome novo",
            str(self.selected_file.with_suffix(".csv")), "Arquivos CSV (*.csv)",
            options=QFileDialog.Option.DontConfirmOverwrite)
        if not filename:
            return
        output = Path(filename)
        if not output.suffix:
            output = output.with_suffix(".csv")
        if output.suffix.lower() != ".csv":
            self._error("Escolha um nome de arquivo com extensão .csv.")
            return
        try:
            write_csv(output, export_csv_analysis(self.analysis))
        except FileExistsError:
            self._error("O arquivo de destino já existe. Escolha outro nome; nenhum arquivo foi substituído.")
        except Exception:
            self._error("Não foi possível salvar o CSV. Verifique a pasta e as permissões e tente novamente.")
        else:
            self.status_label.setText("CSV salvo com sucesso.")

    @staticmethod
    def _dropped_pdf(data: QMimeData) -> Path | None:
        urls = data.urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            if path.suffix.lower() == ".pdf":
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._dropped_pdf(event.mimeData()) is not None:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = self._dropped_pdf(event.mimeData())
        if path is None:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.load_pdf(path, background=True)
