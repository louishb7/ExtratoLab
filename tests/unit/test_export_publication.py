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
    with patch('pdf_to_ofx.application.export.Path.hardlink_to', side_effect=OSError(errno.EOPNOTSUPP, 'unsupported')):
        with pytest.raises(OSError):
            writer(tmp_path / 'export', 'FICTITIOUS')
    assert existing.read_bytes() == b'ORIGINAL'
    assert list(tmp_path.iterdir()) == [existing]


def test_ascii_encoding_failure_creates_no_files(tmp_path):
    with pytest.raises(UnicodeEncodeError):
        write_ofx(tmp_path / 'export', 'é')
    assert list(tmp_path.iterdir()) == []
