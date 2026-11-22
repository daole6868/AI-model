"""Cài PyTorch phù hợp với máy: có GPU NVIDIA thì cài bản CUDA, không thì cài bản CPU.

Được gọi tự động bởi CHAY_WINDOWS.bat / chay_linux_mac.sh. Có thể chạy tay:
    python setup_torch.py
"""
import platform
import re
import shutil
import subprocess
import sys

# Các bản CUDA PyTorch có thể phát hành, mới nhất trước. Bản nào không có sẽ được bỏ qua.
CUDA_TAGS = ["cu132", "cu131", "cu130", "cu129", "cu128", "cu126", "cu124", "cu121"]


def run(*args) -> int:
    print("  $", " ".join(args), flush=True)
    return subprocess.call(list(args))


def pip(*args) -> int:
    return run(sys.executable, "-m", "pip", *args)


def torch_status():
    """Trả về (đã cài torch?, CUDA dùng được?)."""
    code = "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 3)"
    r = subprocess.call([sys.executable, "-c", code], stderr=subprocess.DEVNULL)
    return r in (0, 3), r == 0


def driver_cuda_version():
    """Đọc 'CUDA Version: 12.8' từ nvidia-smi; None nếu không có GPU NVIDIA."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return None
    m = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def tags_for(driver):
    """Các bản CUDA mà driver hỗ trợ (driver phải >= bản CUDA của PyTorch)."""
    ok = []
    for tag in CUDA_TAGS:
        major, minor = int(tag[2:-1]), int(tag[-1])
        if driver == (0, 0) or (major, minor) <= driver:
            ok.append(tag)
    return ok


def main():
    if sys.version_info < (3, 10):
        print(f"[LỖI] Cần Python 3.10 trở lên (bạn đang dùng {platform.python_version()}).")
        return 1

    installed, cuda_ok = torch_status()
    driver = driver_cuda_version()
    system = platform.system()

    if driver is None:
        print("• Không thấy GPU NVIDIA (nvidia-smi) → dùng PyTorch bản CPU/Apple.")
    else:
        print(f"• Thấy GPU NVIDIA, driver hỗ trợ CUDA {driver[0]}.{driver[1]}")

    if installed and (cuda_ok or driver is None):
        print("• PyTorch đã sẵn sàng, bỏ qua bước cài.")
        return 0

    if driver is not None and system == "Windows":
        # Trên Windows, 'pip install torch' chỉ cho bản CPU → phải lấy từ kho CUDA của PyTorch.
        for tag in tags_for(driver):
            print(f"\n• Thử cài PyTorch bản CUDA ({tag})...")
            if installed:
                pip("uninstall", "-y", "torch")
            if pip("install", "torch", "--index-url", f"https://download.pytorch.org/whl/{tag}") == 0:
                installed, cuda_ok = torch_status()
                if cuda_ok:
                    print(f"\n✅ Đã cài PyTorch {tag}, GPU dùng được.")
                    return 0
                print(f"  Bản {tag} cài được nhưng không dùng được GPU, thử bản cũ hơn...")
        print("\n[CẢNH BÁO] Không cài được bản CUDA. Hãy cập nhật driver NVIDIA rồi chạy lại.")
        print("           Tạm thời cài bản CPU để vẫn dùng được (chậm hơn).")
        if installed:
            pip("uninstall", "-y", "torch")

    # Linux: bản trên PyPI đã kèm CUDA; macOS: có sẵn Apple GPU (MPS); Windows: bản CPU.
    if pip("install", "torch") != 0:
        print("[LỖI] Cài PyTorch thất bại. Kiểm tra kết nối mạng rồi chạy lại.")
        return 1
    installed, cuda_ok = torch_status()
    print("\n✅ Đã cài PyTorch" + (" (GPU dùng được)." if cuda_ok else " (chạy bằng CPU)."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
