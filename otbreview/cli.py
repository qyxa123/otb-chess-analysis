import argparse
import json
import os

from .pipeline import Pipeline
from .web_generator import render_webpage


def parse_args():
    parser = argparse.ArgumentParser(description="OTBReview analyzer")
    sub = parser.add_subparsers(dest="command")
    analyze = sub.add_parser("analyze", help="Analyze OTB video")
    analyze.add_argument("--input", required=False, help="Path to mp4 video")
    analyze.add_argument("--outdir", required=True, help="Output directory")
    analyze.add_argument("--engine", default=None, help="Path to stockfish binary")
    analyze.add_argument("--depth", type=int, default=12)
    analyze.add_argument("--demo", action="store_true", help="Use synthetic frames instead of video")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.command != "analyze":
        print("Usage: otbreview analyze --input file.mp4 --outdir out")
        return
    pipeline = Pipeline(args.outdir, args.engine, args.depth)
    if args.demo:
        result = pipeline.run_demo()
    else:
        if not args.input:
            raise SystemExit("--input is required unless --demo is used")
        result = pipeline.run(args.input)
    html = render_webpage({"moves": result["moves"], "stable_frames": result["stable_frames"]}, os.path.join(args.outdir, "web"))
    print("PGN saved to", result["pgn_path"])
    print("Analysis saved to", result["analysis_json"])
    print("Webpage:", html)


if __name__ == "__main__":
    main()
