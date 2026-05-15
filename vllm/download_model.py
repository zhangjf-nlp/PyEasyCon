#!/usr/bin/env python3
from modelscope import snapshot_download

print("Downloading Qwen3-VL-2B-Instruct-FP8 from ModelScope...")
model_dir = snapshot_download('Qwen/Qwen3-VL-2B-Instruct-FP8')
print(f"Model downloaded to: {model_dir}")
