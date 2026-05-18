# GLM-OCR Ollama CPU 部署指南 (Windows)

## 环境

- Windows 11 64-bit | Intel i7-12700H | 纯 CPU 推理
- 依赖 D 盘空间，模型 2.2GB

## 安装

1. 下载 [ollama-windows-amd64.zip](https://github.com/ollama/ollama/releases) 解压到 `D:\ollama`
2. 设置模型存储路径并启动服务（端口 18080）：

```powershell
$env:OLLAMA_MODELS = "D:\ollama\models"
$env:OLLAMA_HOST = "127.0.0.1:18080"
D:\ollama\ollama.exe serve
```

3. 拉取模型：

```powershell
$env:OLLAMA_HOST = "127.0.0.1:18080"
D:\ollama\ollama.exe pull glm-ocr:latest
```

## 验证

```powershell
D:\ollama\ollama.exe list
D:\ollama\ollama.exe show glm-ocr:latest
```

## API 调用

```
端点: POST http://127.0.0.1:18080/api/generate
模式: ollama_generate（Ollama 原生格式）
```

```powershell
$body = '{"model":"glm-ocr:latest","prompt":"识别图片中的文字","stream":false}'
Invoke-RestMethod -Uri "http://127.0.0.1:18080/api/generate" `
  -Method Post -Body $body -ContentType "application/json"
```

## 注意

- 端口 11434 被 Windows Hyper-V 端口排除范围占用，改用 18080
- 首次推理模型加载约 20s，之后常驻内存
- 每次新终端需设置 `$env:OLLAMA_HOST = "127.0.0.1:18080"`
