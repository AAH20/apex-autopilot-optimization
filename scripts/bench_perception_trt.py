#!/usr/bin/env python3
"""
TensorRT GPU perception benchmark.

4-stage perception pipeline on TensorRT engines, following the realtime
vision-pipeline methodology (ml-stack/pipeline.py):

  Stage 1: detect   (person class, YOLO TensorRT engine)
  Stage 2: track    (ByteTrack, ultralytics, runs every frame)
  Stage 3: pose     (YOLO-pose TensorRT engine, every frame)
  Stage 4: action   (r3d-18 Kinetics-400 clip classifier, every N frames)

Behaviour changes on a scale of seconds, so the action model runs at a
decoupled cadence (--action-every) rather than every frame.

Reports per-stage latency, sustained FPS, peak VRAM, and how many 30 fps
streams the GPU can hold. Falls back to PyTorch FP16 when .engine files are
absent, and to CPU when no CUDA device exists (clearly flagged, never
silently slow).

Usage:
    ./bench_trt.py                          # 720p + 1080p cadence sweep
    ./bench_trt.py --resolutions 720p 1080p --frames 120
    ./bench_trt.py --build-engines          # export yolo26n(.pt) -> .engine
    ./bench_trt.py --source /path/to/image.jpg
    ./bench_trt.py --json > bench.json      # machine-readable summary
    ./bench_trt.py --check                  # environment report only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore", message=".*half is deprecated.*", category=UserWarning
)

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache" / "bench_bus.jpg"
CACHE.parent.mkdir(parents=True, exist_ok=True)
BUS_URL = "https://ultralytics.com/images/bus.jpg"

# Optional heavy imports, guarded so --check works without torch installed.
HAS_TORCH = HAS_CV2 = HAS_NP = HAS_ULTRA = HAS_TV = HAS_TRT = False
try:
    import torch  # noqa: F401
    HAS_TORCH = True
except Exception:
    pass
try:
    import cv2  # noqa: F401
    HAS_CV2 = True
except Exception:
    pass
try:
    import numpy as np  # noqa: F401
    HAS_NP = True
except Exception:
    pass
try:
    from ultralytics import YOLO  # noqa: F401
    HAS_ULTRA = True
    # Keep stdout clean for --json: ultralytics logs progress/warnings to stdout.
    import logging as _logging
    _logging.getLogger("ultralytics").setLevel(_logging.ERROR)
except Exception:
    pass
try:
    from torchvision.models.video import r3d_18  # noqa: F401
    HAS_TV = True
except Exception:
    pass
try:
    import tensorrt  # noqa: F401
    HAS_TRT = True
except Exception:
    pass


def env_report() -> dict:
    info = {
        "torch": HAS_TORCH,
        "opencv": HAS_CV2,
        "numpy": HAS_NP,
        "ultralytics": HAS_ULTRA,
        "torchvision": HAS_TV,
        "tensorrt": HAS_TRT,
        "cuda_available": False,
        "gpu": None,
        "vram_gib": None,
    }
    if HAS_TORCH:
        import torch
        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            info["gpu"] = p.name
            info["vram_gib"] = round(p.total_memory / 1024**3, 2)
            info["cuda_capability"] = f"{p.major}{p.minor}"
    return info


def check() -> int:
    info = env_report()
    print("TensorRT perception benchmark environment:")
    for k, v in info.items():
        print(f"  {k:<20} {v}")
    missing = [k for k in ("torch", "opencv", "numpy", "ultralytics")
               if not info[k]]
    if missing:
        print(f"\nmissing: {', '.join(missing)}  pip install torch torchvision "
              "opencv-python numpy ultralytics")
        return 2
    if not info["cuda_available"]:
        print("\nno CUDA device: benchmark will run on CPU (unrepresentative of "
              "GPU/Trt performance).")
    return 0


def ensure_sample() -> Path | None:
    if not HAS_CV2 or not HAS_NP:
        return None
    import cv2
    if not CACHE.exists():
        try:
            urllib.request.urlretrieve(BUS_URL, str(CACHE))
        except Exception as e:
            print(f"sample download failed: {e}")
            return None
    img = cv2.imread(str(CACHE))
    return CACHE if img is not None else None


def resize_frame(img, size):
    import cv2
    return cv2.resize(img, size, interpolation=cv2.INTER_LINEAR)


def load_yolo(path: Path):
    """Load a YOLO model: TensorRT engine first, PyTorch FP16 fallback.

    Mirrors ml-stack/pipeline.py: .engine when present, else the .pt of the
    same stem (ultralytics auto-downloads it on first use).
    """
    from ultralytics import YOLO
    if path.exists():
        return YOLO(str(path)), "tensorrt" if path.suffix == ".engine" else "pytorch"
    pt = path.with_suffix(".pt")
    try:
        return YOLO(str(pt)), "pytorch (auto-downloaded)"
    except Exception:
        raise FileNotFoundError(f"model not found: {path} (and no {pt.name} loadable)")


def build_engines(det_pt: Path, pose_pt: Path, det_eng: Path, pose_eng: Path,
                  imgsz: int = 640) -> bool:
    """Export .pt -> .engine (FP16) when engines are missing."""
    if not HAS_ULTRA:
        print("ultralytics missing; cannot build engines.")
        return False
    from ultralytics import YOLO
    ok = True
    for pt, eng in ((det_pt, det_eng), (pose_pt, pose_eng)):
        if eng.exists():
            print(f"engine exists: {eng}", file=sys.stderr)
            continue
        if not pt.exists():
            print(f"no {pt.name} to export; try 'pip install ultralytics' and "
                  f"download {pt.name} (it auto-downloads on first load).",
                  file=sys.stderr)
            ok = False
            continue
        print(f"exporting {pt.name} -> {eng.name} (FP16, imgsz={imgsz}) ...",
              file=sys.stderr)
        try:
            YOLO(str(pt)).export(format="engine", half=True, imgsz=imgsz,
                                 device=0)
            # ultralytics writes <stem>.engine next to the .pt
            produced = pt.with_suffix(".engine")
            if produced.exists() and produced != eng:
                produced.replace(eng)
            print(f"  wrote {eng}")
        except Exception as e:
            print(f"  export failed: {e}")
            ok = False
    return ok


class PerceptionBench:
    def __init__(self, det_engine: Path, pose_engine: Path, device: str,
                 half: bool, conf: float, action_every: int):
        self.device = device
        self.half = half and device == "cuda"
        self.conf = conf
        self.action_every = action_every
        self.det, det_backend = load_yolo(det_engine)
        self.pose, pose_backend = load_yolo(pose_engine)
        print(f"  detect : {det_engine.name} ({det_backend})", file=sys.stderr)
        print(f"  pose   : {pose_engine.name} ({pose_backend})", file=sys.stderr)
        self.act = None
        if HAS_TV and device == "cuda":
            from torchvision.models.video import r3d_18
            self.act = r3d_18(weights="DEFAULT").cuda().eval()
            if self.half:
                self.act = self.act.half()
            print("  action : r3d-18 (Kinetics-400, TensorRT-class equivalent "
                  "FP16 torchvision model on CUDA)", file=sys.stderr)
        elif self.action_every:
            print("  action : SKIPPED (torchvision unavailable or no CUDA)",
                  file=sys.stderr)

    def _clip(self, frame):
        small = torch.from_numpy(cv2.resize(frame, (224, 224))).permute(2, 0, 1)
        buf = torch.zeros(1, 3, 16, 224, 224, device="cuda").half()
        buf = torch.roll(buf, shifts=-1, dims=2)
        buf[0, :, -1] = small.to("cuda").half() / 255.0
        return buf

    def stage_detect(self, img):
        return self.det.predict(img, verbose=False, conf=self.conf,
                                classes=[0], half=self.half,
                                device=self.device if self.device == "cuda" else None)

    def stage_track(self, img):
        return self.det.track(img, persist=True, tracker="bytetrack.yaml",
                              verbose=False, conf=self.conf, classes=[0],
                              half=self.half)[0]

    def stage_pose(self, img):
        return self.pose.predict(img, verbose=False, conf=self.conf,
                                 half=self.half)[0]

    def stage_action(self, frame):
        if self.act is None:
            return
        with torch.no_grad():
            self.act(self._clip(frame))

    def frame_core(self, img):
        self.stage_track(img)
        self.stage_pose(img)

    def frame_full(self, img):
        self.frame_core(img)
        self.stage_action(img)

    @staticmethod
    def _sync():
        if torch.cuda.is_available():
            torch.cuda.synchronize()

    def run(self, img, n_frames, warmup):
        import torch
        for _ in range(warmup):
            self.frame_full(img)
        self._sync()
        torch.cuda.reset_peak_memory_stats()
        t0 = time.perf_counter()
        for i in range(n_frames):
            self.frame_core(img)
            if self.action_every and i % self.action_every == 0:
                self.stage_action(img)
        self._sync()
        dt = time.perf_counter() - t0
        vram = torch.cuda.max_memory_allocated() / 1024**3
        return n_frames / dt, vram

    def stage_ms(self, img, iters=20, warmup=5):
        """Per-stage latency on a single representative frame."""

        def timed(fn):
            for _ in range(warmup):
                fn()
            self._sync()
            t0 = time.perf_counter()
            for _ in range(iters):
                fn()
            self._sync()
            return (time.perf_counter() - t0) / iters * 1000.0

        return {
            "detect": timed(lambda: self.stage_detect(img)),
            "track": timed(lambda: self.stage_track(img)),
            "pose": timed(lambda: self.stage_pose(img)),
            "action": timed(lambda: self.stage_action(img)) if self.act else None,
        }


def resolutions_list(spec):
    table = {"720p": (720, 1280), "1080p": (1080, 1920), "480p": (480, 640)}
    out = []
    for name in spec:
        if name not in table:
            raise SystemExit(f"unknown resolution {name}; pick from "
                             f"{sorted(table)}")
        out.append((name, *table[name]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="TensorRT GPU perception benchmark (detect -> track -> "
                    "pose -> action, decoupled action cadence).")
    ap.add_argument("--resolutions", nargs="+", default=["720p", "1080p"],
                    help="frame sizes to benchmark")
    ap.add_argument("--frames", type=int, default=120,
                    help="timed frames per configuration")
    ap.add_argument("--warmup", type=int, default=10,
                    help="warmup frames before timing")
    ap.add_argument("--action-every", type=int, nargs="+",
                    default=[1, 8, 16, 0],
                    help="action cadence in frames (0 = core pipeline only)")
    ap.add_argument("--conf", type=float, default=0.25, help="detection conf")
    ap.add_argument("--source", default="",
                    help="image/video source (default: bundled bus.jpg)")
    ap.add_argument("--det-engine", default="yolo26n.engine",
                    help="detection TensorRT engine path")
    ap.add_argument("--pose-engine", default="yolo26n-pose.engine",
                    help="pose TensorRT engine path")
    ap.add_argument("--build-engines", action="store_true",
                    help="export missing .pt -> .engine before benchmarking")
    ap.add_argument("--imgsz", type=int, default=640,
                    help="export imgsz for --build-engines")
    ap.add_argument("--device", default="cuda",
                    help="cuda | cpu (default cuda; falls back to cpu)")
    ap.add_argument("--no-half", action="store_true",
                    help="run FP32 instead of FP16")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON summary instead of the pretty table")
    ap.add_argument("--check", action="store_true",
                    help="report environment and exit")
    args = ap.parse_args()

    if args.check:
        return check()

    missing = [m for m in ("torch", "opencv", "numpy", "ultralytics")
               if not {"torch": HAS_TORCH, "opencv": HAS_CV2, "numpy": HAS_NP,
                         "ultralytics": HAS_ULTRA}[m]]
    if missing:
        print(f"missing dependencies: {', '.join(missing)}", file=sys.stderr)
        print("pip install torch torchvision opencv-python numpy ultralytics",
              file=sys.stderr)
        return 2

    import cv2
    import numpy as np
    import torch
    if args.device == "cuda" and not torch.cuda.is_available():
        print("no CUDA device; falling back to CPU (results not "
              "representative of TensorRT GPU performance)", file=sys.stderr)
        args.device = "cpu"
    if args.device == "cuda":
        p = torch.cuda.get_device_properties(0)
        print(f"gpu: {p.name}  {p.total_memory/1024**3:.1f} GiB  sm_{p.major}{p.minor}",
              file=sys.stderr)

    det_eng = Path(args.det_engine)
    if not det_eng.is_absolute():
        det_eng = ROOT / det_eng
    pose_eng = Path(args.pose_engine)
    if not pose_eng.is_absolute():
        pose_eng = ROOT / pose_eng

    if args.build_engines:
        pt_map = {det_eng: det_eng.with_suffix(".pt"),
                  pose_eng: pose_eng.with_suffix(".pt")}
        ok = build_engines(pt_map[det_eng], pt_map[pose_eng], det_eng,
                           pose_eng, imgsz=args.imgsz)
        if not ok:
            print("engine build incomplete; benchmark will use PyTorch fallback "
                  "for missing engines.")

    img = None
    if args.source:
        img = cv2.imread(args.source)
        if img is None and args.source.lower().endswith((".mp4", ".avi", ".mov")):
            cap = cv2.VideoCapture(args.source)
            ok, img = cap.read()
            cap.release()
        if img is None:
            print(f"cannot read source: {args.source}", file=sys.stderr)
            return 1
    else:
        cached = ensure_sample()
        if cached is not None:
            img = cv2.imread(str(cached))

    if img is None:
        img = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)
        print("no readable sample; using synthetic noise frame")

    try:
        bench = PerceptionBench(det_eng, pose_eng, args.device,
                                not args.no_half, args.conf, args.action_every[0])
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        print("hint: run with --build-engines, or place .engine files next to "
              "this script", file=sys.stderr)
        return 1

    results = []
    for name, h, w in resolutions_list(args.resolutions):
        frame = resize_frame(img, (w, h))
        for every in args.action_every:
            bench.action_every = every
            cadence = "every frame" if every == 1 else (str(every) if every else "core only")
            label = f"{name} action@{cadence}"
            fps, vram = bench.run(frame, args.frames, args.warmup)
            results.append({
                "resolution": name, "size": f"{w}x{h}",
                "action_every": every,
                "fps": round(fps, 1),
                "latency_ms": round(1000 / fps, 2),
                "peak_vram_gib": round(vram, 2),
                "streams_at_30fps": round(fps / 30, 2),
                "device": args.device,
                "half": bench.half,
            })

    # Per-stage latency at the primary resolution (single frame, no cadence).
    bench.action_every = 0
    primary = resize_frame(img, resolutions_list(["720p"])[0][1:])
    try:
        stage = bench.stage_ms(primary)
    except Exception as e:
        stage = {"error": str(e)}

    summary = {
        "gpu": torch.cuda.get_device_properties(0).name if args.device == "cuda" else "cpu",
        "vram_gib": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2) if args.device == "cuda" else None,
        "device": args.device, "half": bench.half, "frames": args.frames,
        "warmup": args.warmup, "conf": args.conf,
        "results": results, "stage_latency_ms": stage,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"\n{'config':<26}{'fps':>7}{'latency':>9}{'VRAM':>8}{'30fps streams':>16}")
        for r in results:
            print(f"{r['resolution']:<6} {r['size']:<8} action@{r['action_every']:<10}"
                  f"{r['fps']:>7.1f}{r['latency_ms']:>9.1f}{r['peak_vram_gib']:>7.2f}G"
                  f"{r['streams_at_30fps']:>15.1f}")
        print(f"\nper-stage latency @ {resolutions_list(['720p'])[0][1]} "
              f"(single frame, ms):")
        for k, v in stage.items():
            print(f"  {k:<10} {v if v is None else round(v, 2)}")
        cadence_txt = str(bench.action_every) if bench.action_every else "N/A (core only)"
        print(f"\npeak VRAM and latency measured with torch.cuda; action model "
              f"runs every {cadence_txt} frame(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
