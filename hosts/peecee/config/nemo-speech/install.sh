#!/usr/bin/env bash
# Install NVIDIA's CUDA CLI and the two peecee checkpoints in WSL.
set -euo pipefail

cache="$HOME/.cache/peecee-nemo/v0.3.0"
prefix="$HOME/.local/share/peecee-speech/0.3.0"
asr=nemotron-3.5-asr-streaming-0.6b
diar=diar_streaming_sortformer_4spk-v2.1
upstream=20999cc921d2b14aa58708f61756a8b2e787ba20
asr_rev=ea30d66debe3740a08b573244286791d423d6b3e
diar_rev=cd03eee90fbec18297ac31b8c21546e596b7f71c

mkdir -p "$cache" "$(dirname "$prefix")" "$HOME/.local/bin"
cd "$cache"
exec 9>install.lock
flock 9

fetch() {
    local url=$1 file=$2 digest=$3
    if [[ -f $file ]] && echo "$digest  $file" | sha256sum --check --status; then
        return
    fi
    curl -fLsS --retry 3 --output "$file.part" "$url"
    echo "$digest  $file.part" | sha256sum --check
    mv -f -- "$file.part" "$file"
}

fetch "https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.3.0/nemo-speech-0.3.0-linux-x86_64-cuda.tar.gz" \
    runtime.tar.gz eca00a1f67d3ca200ddba11dd71c4f3d67e044cc0939d17d073978e40b995917
fetch "https://codeload.github.com/NVIDIA/NeMo-Speech.cpp/tar.gz/$upstream" \
    converter.tar.gz 2e02f2486a0ce9e5bcbd57d04721b849f9572857a6862c9daf5076549982d0c2
fetch "https://huggingface.co/nvidia/$asr/resolve/$asr_rev/$asr.q8_0.gguf" \
    "$asr.q8_0.gguf" 3fc991d3badad7277c11030a7519832cddaf2057aafed6d4b25147e953a070b1
fetch "https://huggingface.co/nvidia/$diar/resolve/$diar_rev/$diar.nemo" \
    "$diar.nemo" 8abd32832159c6ac1148c926b7276f35ba34582c444e559dce1f1253fea42ef8

verify_install() {
    (cd "$1" && sha256sum --check --status <<SUMS
f5818cd45f81b3a3f976d822ed36c539a29961d3dbb4119617d379e3f0eb2a80  bin/nemo-speech
3fc991d3badad7277c11030a7519832cddaf2057aafed6d4b25147e953a070b1  models/$asr.q8_0.gguf
44db9117df5a53bd1787e9c7c186097d0d15bd4301c7e56af0132d941063930b  models/$diar.f32.gguf
SUMS
    ) || { echo "CLI or model checksum mismatch in $1" >&2; return 1; }
}

if [[ ! -d $prefix ]]; then
    stage=$(mktemp -d "${prefix}.XXXXXXXX")
    trap 'rm -rf -- "$stage"' EXIT
    tar -xzf runtime.tar.gz --strip-components=1 -C "$stage"
    mkdir "$stage/models"
    cp --reflink=auto "$asr.q8_0.gguf" "$stage/models/"
    tar -xzf converter.tar.gz
    uv venv --allow-existing --python 3.12.15 converter-env
    uv pip install --python converter-env/bin/python --torch-backend cpu \
        'torch==2.11.0+cpu' 'numpy==1.26.4' 'PyYAML==6.0.3' 'gguf==0.19.0'
    converter-env/bin/python "NeMo-Speech.cpp-$upstream/convert_model.py" "$diar.nemo" \
        --architecture diarization --outtype f32 --outfile "$stage/models/$diar.f32.gguf"
    verify_install "$stage"
    "$stage/bin/nemo-speech" --version
    mv -T -- "$stage" "$prefix"
    trap - EXIT
else
    verify_install "$prefix"
fi

link="$HOME/.local/bin/nemo-speech"
if [[ ! -e $link && ! -L $link ]]; then
    ln -s "$prefix/bin/nemo-speech" "$link"
elif [[ $(readlink -f "$link") != "$prefix/bin/nemo-speech" ]]; then
    echo "Existing CLI at $link; installed CLI is $prefix/bin/nemo-speech" >&2
    exit 1
fi
"$link" --version
