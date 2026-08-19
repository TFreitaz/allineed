from telegram_files import extract_document_file_id


def test_extract_document_file_id():
    message = {
        "document": {
            "file_id": "abc123",
            "file_name": "nota.pdf",
            "mime_type": "application/pdf",
        }
    }

    assert extract_document_file_id(message) == "abc123"


def test_extract_document_file_id_without_document():
    assert extract_document_file_id({}) is None


def test_extract_document_file_id_without_file_id():
    message = {
        "document": {
            "file_name": "nota.pdf",
            "mime_type": "application/pdf",
        }
    }

    assert extract_document_file_id(message) is None