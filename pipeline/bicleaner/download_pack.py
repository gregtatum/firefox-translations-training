#!/usr/bin/env python3
"""
Downloads bicleaner-ai model for a lanuage pair.
Fallbacks to the multilingual model if the lanuage pair is not supported.

Example:
    python download_pack.py \
        --src=en \
        --trg=ru \
        --compression_cmd=zstd \
        artifacts/bicleaner-model-en-ru.zst
"""

import argparse
import os
import subprocess
import tarfile
import tempfile
from typing import Optional


def _run_download(src: str, trg: str, dir: str) -> subprocess.CompletedProcess:
    return subprocess.run(['bicleaner-ai-download', trg, src, "full", dir], capture_output=True, check=False)


def _compress_dir(dir_path: str, compression_cmd: str) -> str:
    print(f"Compressing {dir_path}")
    if compression_cmd not in ["gzip", "zstd", "zstdmt", "pigz"]:
        raise ValueError("Unsupported compression tool.")

    tarball_path = dir_path + ".tar"
    with tarfile.open(tarball_path, "w") as tar:
        tar.add(dir_path, arcname=os.path.basename(dir_path))

    if compression_cmd in ("gzip", "pigz"):
        comp_ext = ".gz"
    else:
        comp_ext = ".zst"

    compressed_path = tarball_path + comp_ext
    subprocess.run([compression_cmd, tarball_path], check=True)
    os.remove(dir_path)

    return compressed_path


def donwload(src: str, trg: str, output_path: str, compression_cmd: str) -> None:
    tmp_dir = tempfile.gettempdir()

    print(f"Downloading a model for {src}-{trg}")
    result = _run_download(src, trg, tmp_dir)

    if result.returncode == 0:
        print("Success")
    else:
        src, trg = trg, src
        print(f"Failed. Trying {src}-{trg}")
        result = _run_download(src, trg, tmp_dir)

        if result.returncode != 0 and "language pack does not exist" in str(result.stderr):
            print("Failed. Downloading multilingual model en-xx")
            src = "en"
            trg = "xx"
            # fallback to multilingual model if language pair is not supported
            result = _run_download(src, trg, tmp_dir)

        result.check_returncode()

    # Compress downloaded pack and
    pack_dir = os.path.join(tmp_dir, f"{src}-{trg}")
    if compression_cmd:
        pack_dir = _compress_dir(pack_dir, compression_cmd)
    # move to the expected path
    print(f"Moving {pack_dir} to {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    os.rename(pack_dir, output_path)
    print("Done")


def main(args: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,  # Preserves whitespace in the help text.
    )
    parser.add_argument("--src", type=str, help="Source language code")
    parser.add_argument("--trg", type=str, help="Target language code")
    parser.add_argument(
        "--compression_cmd",
        type=Optional[str],
        required=False,
        default=None,
        help="Compression command (eg. pigz, zstd). "
        "Optional, if not provided the directory will not be compressed",
    )
    parser.add_argument(
        "output_path",
        type=str,
        help="Full output file or directory path for example artifacts/en-pt.zst",
    )

    parsed_args = parser.parse_args(args)

    donwload(
        src=parsed_args.src,
        trg=parsed_args.trg,
        output_path=parsed_args.output_path,
        compression_cmd=parsed_args.compression_cmd,
    )


if __name__ == "__main__":
    main()