"""Tests for audio and video compression in archive files."""
import os
import tempfile
import zipfile
from unittest.mock import patch

from ricecooker.classes.files import H5PFile
from ricecooker.classes.files import HTMLZipFile


def test_html5_archive_with_mp4_compression(video_file, audio_file):
    """Test that MP4 and MP3 files within HTML5 archives are compressed when compression is enabled."""
    # Create temporary HTML5 archive with media files
    temp_archive = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    temp_archive.close()

    try:
        with zipfile.ZipFile(temp_archive.name, "w") as zf:
            zf.writestr("index.html", "<html><body>Test content</body></html>")
            # Add media files by reading from fixture files
            with open(video_file.path, "rb") as vf:
                zf.writestr("video/sample.mp4", vf.read())
            with open(audio_file.path, "rb") as af:
                zf.writestr("audio/sample.mp3", af.read())

        with patch(
            "ricecooker.utils.pipeline.convert.compress_video"
        ) as mock_video_compress, patch(
            "ricecooker.utils.pipeline.convert.compress_audio"
        ) as mock_audio_compress:

            # Mock successful compression
            mock_video_compress.return_value = None
            mock_audio_compress.return_value = None

            # Process the HTML5 file with compression enabled
            with patch("ricecooker.config.COMPRESS", True):
                html_file = HTMLZipFile(temp_archive.name)
                result = html_file.process_file()

            # Verify both compression functions were called
            assert (
                mock_video_compress.called
            ), "Video compression should be called for MP4 files"
            assert (
                mock_audio_compress.called
            ), "Audio compression should be called for MP3 files"
            assert result is not None, "Processing should succeed"

    finally:
        os.unlink(temp_archive.name)


def test_h5p_archive_with_webm_compression(video_file):
    """Test that WebM files within H5P archives are compressed when compression is enabled."""
    # Create temporary H5P archive with WebM file
    temp_archive = tempfile.NamedTemporaryFile(suffix=".h5p", delete=False)
    temp_archive.close()

    try:
        with zipfile.ZipFile(temp_archive.name, "w") as zf:
            zf.writestr("h5p.json", '{"valid": "json"}')
            zf.writestr("content/content.json", '{"valid": "content"}')
            # Add video file but with .webm extension to test WebM handling
            with open(video_file.path, "rb") as vf:
                zf.writestr("videos/sample.webm", vf.read())

        with patch("ricecooker.utils.pipeline.convert.compress_video") as mock_compress:
            # Mock successful compression
            mock_compress.return_value = None

            # Process the H5P file with compression enabled
            with patch("ricecooker.config.COMPRESS", True):
                h5p_file = H5PFile(temp_archive.name)
                result = h5p_file.process_file()

            # Verify compression was called
            assert (
                mock_compress.called
            ), "Video compression should be called for WebM files"
            assert result is not None, "Processing should succeed"

    finally:
        os.unlink(temp_archive.name)


def test_archive_no_compression_when_disabled(video_file, audio_file):
    """Test that media files are not compressed when compression is disabled."""
    # Create temporary HTML5 archive with media files
    temp_archive = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    temp_archive.close()

    try:
        with zipfile.ZipFile(temp_archive.name, "w") as zf:
            zf.writestr("index.html", "<html><body>Test content</body></html>")
            with open(video_file.path, "rb") as vf:
                zf.writestr("video/sample.mp4", vf.read())
            with open(audio_file.path, "rb") as af:
                zf.writestr("audio/sample.mp3", af.read())

        with patch(
            "ricecooker.utils.pipeline.convert.compress_video"
        ) as mock_video_compress, patch(
            "ricecooker.utils.pipeline.convert.compress_audio"
        ) as mock_audio_compress:

            # Process the HTML5 file with compression disabled
            with patch("ricecooker.config.COMPRESS", False):
                html_file = HTMLZipFile(temp_archive.name)
                result = html_file.process_file()

            # Verify compression functions were not called
            assert (
                not mock_video_compress.called
            ), "Video compression should not be called when disabled"
            assert (
                not mock_audio_compress.called
            ), "Audio compression should not be called when disabled"
            assert result is not None, "Processing should still succeed"

    finally:
        os.unlink(temp_archive.name)


def _make_kpub(tmp_path, files):
    path = tmp_path / "article.kpub"
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return str(path)


def test_kpub_file_is_processed(tmp_path):
    from le_utils.constants import format_presets

    from ricecooker.classes.files import KPUBFile

    path = _make_kpub(tmp_path, {"index.html": "<html><body><p>Text</p></body></html>", "index.md": "Text\n"})
    kpub = KPUBFile(path)
    assert kpub.process_file() is not None
    assert kpub.get_preset() == format_presets.KPUB_ZIP


def test_kpub_with_scripts_is_rejected(tmp_path):
    from ricecooker.classes.files import KPUBFile

    path = _make_kpub(tmp_path, {"index.html": "<html><body><p>Text</p><script>x()</script></body></html>"})
    kpub = KPUBFile(path)
    assert kpub.process_file() is None
    assert "script" in str(kpub.error)


def test_markdown_kpub_keeps_markdown_and_makes_mathml(tmp_path):
    from ricecooker.utils import markdown_kpub

    if not markdown_kpub.mathjax_available():
        import pytest

        pytest.skip("needs node and mathjax-full")
    markdown = markdown_kpub.html_to_markdown(
        "<html><body><main><h1>Speed</h1><p>So \\(v = \\cancel{d}/t\\)</p></main></body></html>", str(tmp_path / "md")
    )
    assert markdown == "# Speed\n\nSo $v = \\cancel{d}/t$\n"
    markdown_kpub.markdown_to_kpub(markdown, str(tmp_path / "kpub"), markdown_dir=str(tmp_path / "md"))
    index = (tmp_path / "kpub" / "index.html").read_text(encoding="utf-8")
    assert "<menclose" in index
    assert (tmp_path / "kpub" / "index.md").read_text(encoding="utf-8") == markdown
