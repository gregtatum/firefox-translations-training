#!/bin/bash
##
# Generates a lexical shortlist for a corpus.
#
#
# It also generate SentencePiece tokenized alignments that are required for extract_lex
#

set -x
set -euo pipefail

echo "###### Generating alignments and shortlist"
[[ -z "${MARIAN}" ]] && echo "MARIAN is empty"
[[ -z "${BIN}" ]] && echo "BIN is empty"
[[ -z "${SRC}" ]] && echo "SRC is empty"
[[ -z "${TRG}" ]] && echo "TRG is empty"

corpus_prefix=$1
vocab_path=$2
output_dir=$3
threads=$4

COMPRESSION_CMD="${COMPRESSION_CMD:-pigz}"
ARTIFACT_EXT="${ARTIFACT_EXT:-gz}"

if [ "$threads" = "auto" ]; then
  threads=$(nproc)
fi

cd "$(dirname "${0}")"

mkdir -p "${output_dir}"
dir="${output_dir}/tmp"
mkdir -p "${dir}"

corpus_src="${corpus_prefix}.${SRC}.${ARTIFACT_EXT}"
corpus_trg="${corpus_prefix}.${TRG}.${ARTIFACT_EXT}"


echo "### Subword segmentation with SentencePiece"
${COMPRESSION_CMD} -dc "${corpus_src}" |
  parallel --no-notice --pipe -k -j "${threads}" --block 50M "${MARIAN}/spm_encode" --model "${vocab_path}" |
  ${COMPRESSION_CMD} >"${dir}/corpus.spm.${SRC}.${ARTIFACT_EXT}"

${COMPRESSION_CMD} -dc "${corpus_trg}" |
  parallel --no-notice --pipe -k -j "${threads}" --block 50M "${MARIAN}/spm_encode" --model "${vocab_path}" |
  ${COMPRESSION_CMD} >"${dir}/corpus.spm.${TRG}.${ARTIFACT_EXT}"

echo "### Creating merged corpus"
paste <(${COMPRESSION_CMD} -dc "${dir}/corpus.spm.${SRC}.${ARTIFACT_EXT}") <(${COMPRESSION_CMD} -dc "${dir}/corpus.spm.${TRG}.${ARTIFACT_EXT}") |
  sed 's/\t/ ||| /' >"${dir}/corpus"

echo "### Training alignments"
# forward
"${BIN}/fast_align" -vod -i "${dir}/corpus" >"${dir}/align.s2t"
# reversed
"${BIN}/fast_align" -vodr -i "${dir}/corpus" >"${dir}/align.t2s"

echo "### Symmetrizing alignments"
"${BIN}/atools" -i "${dir}/align.s2t" -j "${dir}/align.t2s" -c grow-diag-final-and |
  ${COMPRESSION_CMD} >"${output_dir}/corpus.aln.${ARTIFACT_EXT}"

echo "### Creating shortlist"
# extract_lex doesn't support zstd natively; we need to
# decrypt first
if [ "${ARTIFACT_EXT}" = "zst" ]; then
  zstdmt -d "${dir}/corpus.spm.${TRG}.${ARTIFACT_EXT}"
  zstdmt -d "${dir}/corpus.spm.${SRC}.${ARTIFACT_EXT}"
  zstdmt -d "${output_dir}/corpus.aln.${ARTIFACT_EXT}"
  "${BIN}/extract_lex" \
    "${dir}/corpus.spm.${TRG}" \
    "${dir}/corpus.spm.${SRC}" \
    "${output_dir}/corpus.aln" \
    "${dir}/lex.s2t" \
    "${dir}/lex.t2s"
  rm "${dir}/corpus.spm.${TRG}"
  rm "${dir}/corpus.spm.${SRC}"
  rm "${output_dir}/corpus.aln"
else
  "${BIN}/extract_lex" \
    "${dir}/corpus.spm.${TRG}.${ARTIFACT_EXT}" \
    "${dir}/corpus.spm.${SRC}.${ARTIFACT_EXT}" \
    "${output_dir}/corpus.aln.${ARTIFACT_EXT}" \
    "${dir}/lex.s2t" \
    "${dir}/lex.t2s"
fi

if [ -f "${dir}/lex.s2t" ]; then
  ${COMPRESSION_CMD} "${dir}/lex.s2t"
fi

echo "### Shortlist pruning"
"${MARIAN}/spm_export_vocab" --model="${vocab_path}" --output="${dir}/vocab.txt"
${COMPRESSION_CMD} -dc "${dir}/lex.s2t.${ARTIFACT_EXT}" |
  grep -v NULL |
  python3 "prune_shortlist.py" 100 "${dir}/vocab.txt" |
  ${COMPRESSION_CMD} >"${output_dir}/lex.s2t.pruned.${ARTIFACT_EXT}"

echo "### Deleting tmp dir"
rm -rf "${dir}"

echo "###### Done: Generating alignments and shortlist"
