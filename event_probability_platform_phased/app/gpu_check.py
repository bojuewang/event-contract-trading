from __future__ import annotations

try:
    import torch
except ImportError:
    print("PyTorch is not installed. Run scripts/install_gpu_pytorch.sh or install from PyTorch official selector.")
    raise SystemExit(0)

print("torch version:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("cuda version:", torch.version.cuda)
    print("device count:", torch.cuda.device_count())
    for i in range(torch.cuda.device_count()):
        print(f"device {i}:", torch.cuda.get_device_name(i))
    x = torch.randn(4096, 4096, device="cuda")
    y = x @ x.T
    torch.cuda.synchronize()
    print("GPU matmul smoke test OK:", float(y[0, 0].detach().cpu()))
