"""Publication integrity under races, partial writes and unsupported filesystems."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import errno
from tempfile import NamedTemporaryFile
from unittest.mock import patch

import pytest

from pdf_to_ofx.application.export import write_csv, write_ofx


@pytest.mark.parametrize('writer,contents', [(write_csv, 'Fictício\n'), (write_ofx, 'FICTITIOUS\n')])
def test_concurrent_publication_has_one_complete_winner(tmp_path, writer, contents):
    output = tmp_path / 'export'
    def publish(value):
        try:
            writer(output, value)
            return True
        except FileExistsError:
            return False
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(publish, [contents, contents + 'SECOND\n']))
    assert sum(outcomes) == 1
    assert output.read_bytes() in {contents.encode('utf-8'), (contents + 'SECOND\n').encode('utf-8')}
    assert list(tmp_path.iterdir()) == [output]


@pytest.mark.parametrize('writer', [write_csv, write_ofx])
def test_partial_temporary_write_never_publishes(tmp_path, writer):
    @contextmanager
    def failing_file(**kwargs):
        with NamedTemporaryFile(**kwargs) as file:
            original = file.write
            def fail(payload):
                original(payload[:3])
                raise OSError('injected partial write')
            file.write = fail
            yield file
    with patch('pdf_to_ofx.application.export.NamedTemporaryFile', failing_file):
        with pytest.raises(OSError):
            writer(tmp_path / 'export', 'FICTITIOUS COMPLETE CONTENT')
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('writer', [write_csv, write_ofx])
def test_unsupported_hardlinks_fail_closed_and_preserve_existing_files(tmp_path, writer):
    existing = tmp_path / 'existing'
    existing.write_bytes(b'ORIGINAL')
    with patch('pdf_to_ofx.application.export.Path.hardlink_to', side_effect=OSError(errno.EOPNOTSUPP, 'unsupported')), \
         patch('pdf_to_ofx.application.export._rename_no_replace', side_effect=OSError(errno.ENOTSUP, 'unsupported')):
        with pytest.raises(OSError):
            writer(tmp_path / 'export', 'FICTITIOUS')
    assert existing.read_bytes() == b'ORIGINAL'
    assert list(tmp_path.iterdir()) == [existing]


@pytest.mark.parametrize('writer', [write_csv, write_ofx])
def test_native_exclusive_fallback_preserves_existing_destination_under_race(tmp_path, writer):
    import sys
    if not (sys.platform.startswith('linux') or sys.platform == 'win32'):
        pytest.skip('Native exclusive rename requires Linux or Windows.')
    output=tmp_path/'export'
    def publish(value):
        try:
            writer(output,value)
            return True
        except FileExistsError:
            return False
    with patch('pdf_to_ofx.application.export.Path.hardlink_to',side_effect=OSError(errno.EOPNOTSUPP,'unsupported')):
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes=list(workers.map(publish,['FICTITIOUS FIRST','FICTITIOUS SECOND']))
    assert sum(outcomes)==1
    assert output.read_bytes() in {b'FICTITIOUS FIRST',b'FICTITIOUS SECOND'}
    assert list(tmp_path.iterdir())==[output]


def test_native_fallback_refuses_dangling_link(tmp_path):
    import sys
    if not (sys.platform.startswith('linux') or sys.platform == 'win32'):
        pytest.skip('Native exclusive rename requires Linux or Windows.')
    output=tmp_path/'export'
    try:
        output.symlink_to(tmp_path/'missing')
    except OSError:
        if sys.platform=='win32':
            pytest.skip('Windows symlink privilege unavailable.')
        raise
    with patch('pdf_to_ofx.application.export.Path.hardlink_to',side_effect=OSError(errno.EOPNOTSUPP,'unsupported')):
        with pytest.raises(FileExistsError):write_csv(output,'FICTITIOUS')
    assert output.is_symlink()
    assert list(tmp_path.iterdir())==[output]


def test_other_platform_never_uses_posix_overwriting_rename(tmp_path):
    with patch('pdf_to_ofx.application.export.sys.platform','unknown'), \
         patch('pdf_to_ofx.application.export.Path.hardlink_to',side_effect=OSError(errno.EOPNOTSUPP,'unsupported')), \
         patch('pdf_to_ofx.application.export.os.rename') as unsafe:
        with pytest.raises(OSError):write_csv(tmp_path/'export','FICTITIOUS')
    unsafe.assert_not_called()
    assert list(tmp_path.iterdir())==[]


def test_ascii_encoding_failure_creates_no_files(tmp_path):
    with pytest.raises(UnicodeEncodeError):
        write_ofx(tmp_path / 'export', 'é')
    assert list(tmp_path.iterdir()) == []
