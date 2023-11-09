#!/usr/bin/env python3
"""
Downloads a dataset and runs augmentation if needed

Example:
    SRC=ru TRG=en python pipeline/data/dataset_importer.py \
        --type=corpus \
        --dataset=sacrebleu_aug-mix_wmt19 \
        --output_prefix=$(pwd)/test_data/augtest
"""

import argparse
import os
import re
import subprocess
import sys
from typing import Iterable, List

from opustrainer.modifiers.surface import TitleCaseModifier, UpperCaseModifier
from opustrainer.modifiers.typos import TypoModifier
from opustrainer.types import Modifier


class CompositeModifier:
    def __init__(self, modifiers: List[Modifier]):
        self._modifiers = modifiers

    def __call__(self, batch: List[str]) -> Iterable[str]:
        for mod in self._modifiers:
            batch = list(mod(batch))

        return batch


NOISE_RATE = 0.1  # 10% noise by default

modifier_map = {
    "aug-typos": TypoModifier(NOISE_RATE),
    "aug-title": TitleCaseModifier(NOISE_RATE),
    "aug-title-strict": TitleCaseModifier(1.0),
    "aug-upper": UpperCaseModifier(NOISE_RATE),
    "aug-upper-strict": UpperCaseModifier(1.0),
    "aug-mix": CompositeModifier(
        [TypoModifier(NOISE_RATE), UpperCaseModifier(NOISE_RATE), TitleCaseModifier(NOISE_RATE)]
    ),
}


def run_cmd(cmd: List[str]):
    result = None
    try:
        result = subprocess.run(
            cmd,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        result.check_returncode()
    except:
        if result:
            print(result.stdout)
        raise

    print(result.stdout)


# we plan to use it only for small evaluation datasets
def augment(output_prefix: str, aug_modifer: str):
    if aug_modifer not in modifier_map:
        raise ValueError(f"Invalid modifier {aug_modifer}. Allowed values: {modifier_map.keys()}")

    modifer = modifier_map[aug_modifer]

    # these envs are standard across the pipeline
    src = os.environ["SRC"]
    trg = os.environ["TRG"]
    comp_cmd = os.getenv("COMPRESSION_CMD", "pigz")
    comp_ext = os.getenv("ARTIFACT_EXT", "gz")

    uncompressed_src = f"{output_prefix}.{src}"
    uncompressed_trg = f"{output_prefix}.{trg}"
    compressed_src = f"{output_prefix}.{src}.{comp_ext}"
    compressed_trg = f"{output_prefix}.{trg}.{comp_ext}"

    if os.path.isfile(uncompressed_src):
        os.remove(uncompressed_src)
    if os.path.isfile(uncompressed_trg):
        os.remove(uncompressed_trg)
    run_cmd([comp_cmd, "-d", compressed_src])
    run_cmd([comp_cmd, "-d", compressed_trg])

    with open(uncompressed_src) as f:
        corpus_src = [line.rstrip("\n") for line in f]
    with open(uncompressed_trg) as f:
        corpus_trg = [line.rstrip("\n") for line in f]

    corpus = [f"{src_sent}\t{trg_sent}" for src_sent, trg_sent in zip(corpus_src, corpus_trg)]
    modified = list(modifer(corpus))
    modified_src = "\n".join([line.split("\t")[0] for line in modified]) + "\n"
    modified_trg = "\n".join([line.split("\t")[1] for line in modified]) + "\n"

    with open(uncompressed_src, "w") as f:
        f.write(modified_src)
    with open(uncompressed_trg, "w") as f:
        f.writelines(modified_trg)

    os.remove(compressed_src)
    os.remove(compressed_trg)
    run_cmd([comp_cmd, uncompressed_src])
    run_cmd([comp_cmd, uncompressed_trg])
    os.remove(uncompressed_src)
    os.remove(uncompressed_trg)


def run_import(type: str, dataset: str, output_prefix: str):
    current_dir = os.path.dirname(os.path.abspath(__file__))

    if type == "corpus":
        match = re.search(r"^(\w*)_(aug[a-z\-]*)?_?(.+)$", dataset)

        if not match:
            raise ValueError(f"Invalid dataset name: {dataset}")

        importer = match.group(1)
        aug_modifer = match.group(2)
        name = match.group(3)

        no_aug_id = f"{importer}_{name}"

        print("Downloading parallel dataset")
        run_cmd([os.path.join(current_dir, "download-corpus.sh"), no_aug_id, output_prefix])
        if aug_modifer:
            print("Running augmentation")
            augment(output_prefix, aug_modifer)

    elif type == "mono":
        print("Downloading mono dataset")
        run_cmd([os.path.join(current_dir, "download-mono.sh"), dataset, output_prefix])
    else:
        raise ValueError(f"Invalid dataset type: {type}. Allowed values: mono, corpus")


def main() -> None:
    print(f"Running with arguments: {sys.argv}")
    parser = argparse.ArgumentParser()

    parser.add_argument("--type", metavar="TYPE", type=str, help="Dataset type: mono or corpus")
    parser.add_argument("--dataset", metavar="DATASET", type=str, help="Full dataset identifier")
    parser.add_argument(
        "--output_prefix", metavar="OUTPUT_PREFIX", type=str, help="Write dataset here"
    )

    args = parser.parse_args()
    print("Starting dataset import")
    run_import(args.type, args.dataset, args.output_prefix)
    print("Finished")


if __name__ == "__main__":
    main()