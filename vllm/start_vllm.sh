#!/bin/bash
cd ~/vllm-qwen3vl
source venv/bin/activate
export PYTHONUNBUFFERED=1
export CUDA_VISIBLE_DEVICES=0

vllm serve $HOME/.cache/modelscope/hub/models/Qwen/Qwen3-VL-2B-Instruct-FP8 \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 2048 \
  --gpu-memory-utilization 0.65 \
  --max-num-seqs 8 \
  --enforce-eager \
  --mm-processor-cache-gb 0 \
  --skip-mm-profiling \
  --limit-mm-per-prompt '{"image": 1, "video": 0}'
