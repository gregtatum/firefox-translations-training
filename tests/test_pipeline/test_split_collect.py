import glob
import os
import random
import shutil
import string
import subprocess

import pytest
import sh

from pipeline.translate.splitter import main as split_file
from tests.fixtures import DataDir

COMPRESSION_CMD = "zstdmt"


@pytest.fixture(scope="function")
def data_dir():
    return DataDir("test_split_collect")


def generate_dataset(length, path):
    words = [
        "".join([random.choice(string.ascii_letters) for _ in range(random.randint(1, 10))])
        for _ in range(20)
    ]
    sentences = []
    for i in range(length):
        sentence = " ".join([words[random.randint(0, 19)] for _ in range(random.randint(1, 200))])
        sentences.append(sentence)

    with open(path, "w") as f:
        f.write("\n".join(sentences))

    sh.zstdmt(path)


def decompress(path):
    sh.zstdmt("-d", path)


def imitate_translate(dir, suffix):
    for file in glob.glob(f"{dir}/file.?.zst") + glob.glob(f"{dir}/file.??.zst"):
        print(file)
        decompress(file)
        shutil.copy(file[:-4], file[:-4] + suffix)


def read_file(path):
    with open(path) as f:
        return f.read()


def test_split_collect_mono(data_dir):
    os.environ["COMPRESSION_CMD"] = COMPRESSION_CMD
    length = 1234
    path = data_dir.join("mono.in")
    output = data_dir.join("mono.output")
    output_compressed = f"{output}.zst"
    generate_dataset(length, path)

    split_file(
        [
            f"--output_dir={data_dir.path}",
            "--num_parts=10",
            f"--compression_cmd={COMPRESSION_CMD}",
            f"{path}.zst",
        ]
    )

    # file.1.zst, file.2.zst ... file.10.zst
    expected_files = set([str(data_dir.join(f"file.{i}.zst")) for i in range(1, 11)])
    assert set(glob.glob(str(data_dir.join("file.*.zst")))) == expected_files

    imitate_translate(data_dir.path, suffix=".out")
    subprocess.run(
        ["pipeline/translate/collect.sh", data_dir.path, output_compressed, f"{path}.zst"],
        check=True,
    )

    decompress(output_compressed)
    assert read_file(path) == read_file(output)


def test_split_collect_corpus(data_dir):
    os.environ["COMPRESSION_CMD"] = COMPRESSION_CMD
    length = 1234
    path_src = data_dir.join("corpus.src.in")
    path_trg = data_dir.join("corpus.trg.in")
    output = data_dir.join("corpus.src.output")
    output_compressed = f"{output}.zst"
    generate_dataset(length, path_src)
    generate_dataset(length, path_trg)

    split_file(
        [
            f"--output_dir={data_dir.path}",
            "--num_parts=10",
            f"--compression_cmd={COMPRESSION_CMD}",
            f"{path_src}.zst",
        ]
    )
    split_file(
        [
            f"--output_dir={data_dir.path}",
            "--num_parts=10",
            f"--compression_cmd={COMPRESSION_CMD}",
            "--output_suffix=.ref",
            f"{path_trg}.zst",
        ]
    )

    # file.1.zst, file.2.zst ... file.10.zst
    # file.1.ref.zst, file.2.ref.zst ... file.10.ref.zst
    expected_files = set([data_dir.join(f"file.{i}.zst") for i in range(1, 11)]) | set(
        [data_dir.join(f"file.{i}.ref.zst") for i in range(1, 11)]
    )
    assert set(glob.glob(str(data_dir.join("file.*.zst")))) == expected_files

    imitate_translate(data_dir.path, suffix=".nbest.out")
    subprocess.run(
        ["pipeline/translate/collect.sh", data_dir.path, output_compressed, f"{path_src}.zst"],
        check=True,
    )

    decompress(output_compressed)
    assert read_file(path_src) == read_file(output)
