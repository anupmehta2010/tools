"""ML helpers: ONNX run/info, CLIP zero-shot, sentence-transformer embeddings, tokenize, vector ops."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from _common import lazy_import, tool_main

# ---- ONNX ----

def cmd_onnx_info(args):
    ort = lazy_import("onnxruntime", "pip install onnxruntime")
    sess = ort.InferenceSession(args.input, providers=["CPUExecutionProvider"])
    print("Inputs:")
    for i in sess.get_inputs():
        print(f"  {i.name:<24} shape={i.shape}  dtype={i.type}")
    print("Outputs:")
    for o in sess.get_outputs():
        print(f"  {o.name:<24} shape={o.shape}  dtype={o.type}")


def cmd_onnx_run(args):
    ort = lazy_import("onnxruntime", "pip install onnxruntime")
    np = lazy_import("numpy", "pip install numpy")
    sess = ort.InferenceSession(args.input, providers=["CPUExecutionProvider"])
    feed_raw = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    feed = {k: np.asarray(v, dtype=np.float32) for k, v in feed_raw.items()}
    outputs = sess.run(None, feed)
    out_map = {o.name: outputs[i].tolist() for i, o in enumerate(sess.get_outputs())}
    s = json.dumps(out_map, indent=2)
    if args.output:
        Path(args.output).write_text(s, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(s)


# ---- CLIP image classify ----

def cmd_classify_image(args):
    oc = lazy_import("open_clip", "pip install open-clip-torch")
    torch = lazy_import("torch", "pip install torch")
    lazy_import("PIL.Image", "pip install pillow")
    from PIL import Image as I
    model, _, preprocess = oc.create_model_and_transforms(args.model, pretrained=args.pretrained)
    tokenizer = oc.get_tokenizer(args.model)
    labels = args.labels.split(",")
    text = tokenizer([f"a photo of a {l.strip()}" for l in labels])
    img = preprocess(I.open(args.input).convert("RGB")).unsqueeze(0)
    model.eval()
    with torch.no_grad():
        img_f = model.encode_image(img); img_f /= img_f.norm(dim=-1, keepdim=True)
        txt_f = model.encode_text(text);  txt_f /= txt_f.norm(dim=-1, keepdim=True)
        probs = (100.0 * img_f @ txt_f.T).softmax(dim=-1)[0].tolist()
    ranked = sorted(zip(labels, probs, strict=False), key=lambda x: -x[1])
    for lab, p in ranked:
        print(f"  {p*100:>6.2f}%  {lab.strip()}")


# ---- Sentence-transformers text embedding ----

def cmd_embed_text(args):
    lazy_import("sentence_transformers", "pip install sentence-transformers")
    from sentence_transformers import SentenceTransformer
    text = args.text if args.text else Path(args.input).read_text(encoding="utf-8")
    model = SentenceTransformer(args.model)
    vec = model.encode(text, normalize_embeddings=args.normalize).tolist()
    out = json.dumps(vec)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {len(vec)}-dim vector -> {args.output}")
    else:
        print(out)


def cmd_embed_image(args):
    oc = lazy_import("open_clip", "pip install open-clip-torch")
    torch = lazy_import("torch", "pip install torch")
    lazy_import("PIL.Image", "pip install pillow")
    from PIL import Image as I
    model, _, preprocess = oc.create_model_and_transforms(args.model, pretrained=args.pretrained)
    img = preprocess(I.open(args.input).convert("RGB")).unsqueeze(0)
    model.eval()
    with torch.no_grad():
        feat = model.encode_image(img)
        if args.normalize:
            feat = feat / feat.norm(dim=-1, keepdim=True)
    vec = feat[0].tolist()
    out = json.dumps(vec)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"Wrote {len(vec)}-dim vector -> {args.output}")
    else:
        print(out)


# ---- Tokenize / count ----

def cmd_tokenize(args):
    tk = lazy_import("tiktoken", "pip install tiktoken")
    enc = tk.get_encoding(args.encoding)
    text = args.text if args.text else Path(args.input).read_text(encoding="utf-8")
    ids = enc.encode(text)
    if args.show_tokens:
        for i in ids:
            print(f"  {i:>6}  {enc.decode([i])!r}")
    print(f"Tokens: {len(ids)}")


def cmd_gpt_token_count(args):
    tk = lazy_import("tiktoken", "pip install tiktoken")
    enc = tk.get_encoding(args.encoding)
    text = args.text if args.text else Path(args.input).read_text(encoding="utf-8")
    ids = enc.encode(text)
    print(f"Encoding: {args.encoding}")
    print(f"Tokens:   {len(ids)}")
    print(f"Chars:    {len(text)}")
    if ids:
        print(f"Ratio:    {len(text)/len(ids):.2f} chars/token")


# ---- Vector ops ----

def _cosine(a, b):
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)


def cmd_vector_similarity(args):
    a = json.loads(Path(args.a).read_text(encoding="utf-8"))
    b = json.loads(Path(args.b).read_text(encoding="utf-8"))
    if len(a) != len(b):
        print(f"Dim mismatch: {len(a)} vs {len(b)}"); return 1
    sim = _cosine(a, b)
    print(f"Cosine similarity: {sim:.6f}")
    print(f"Cosine distance:   {1.0 - sim:.6f}")


def cmd_vector_search(args):
    query = json.loads(Path(args.query).read_text(encoding="utf-8"))
    results = []
    with open(args.index, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            v = obj.get("vector") or obj.get("embedding")
            if v is None or len(v) != len(query):
                continue
            results.append((obj.get("id", "?"), _cosine(query, v)))
    results.sort(key=lambda x: -x[1])
    for i, (id_, sim) in enumerate(results[:args.top_k]):
        print(f"  {i+1:>3}. {sim:.4f}  {id_}")


COMMANDS = {
    "onnx-run":          "run ONNX model on JSON feed dict",
    "onnx-info":         "show ONNX model input/output schemas",
    "classify-image":    "zero-shot CLIP image classification given comma-separated labels",
    "embed-text":        "text embedding via sentence-transformers",
    "embed-image":       "image embedding via CLIP",
    "tokenize":          "tokenize text via tiktoken",
    "gpt-token-count":   "count tokens for an OpenAI/GPT encoding",
    "vector-similarity": "cosine similarity between two JSON vectors",
    "vector-search":     "top-K cosine search across a JSONL index",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="ml_tools", description="ML helpers")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("onnx-info", help=COMMANDS["onnx-info"]); p.add_argument("input")
    p.set_defaults(func=cmd_onnx_info)

    p = sub.add_parser("onnx-run", help=COMMANDS["onnx-run"])
    p.add_argument("input"); p.add_argument("feed")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_onnx_run)

    p = sub.add_parser("classify-image", help=COMMANDS["classify-image"])
    p.add_argument("input"); p.add_argument("labels", help="comma-separated label list")
    p.add_argument("--model", default="ViT-B-32")
    p.add_argument("--pretrained", default="laion2b_s34b_b79k")
    p.set_defaults(func=cmd_classify_image)

    p = sub.add_parser("embed-text", help=COMMANDS["embed-text"])
    p.add_argument("text", nargs="?")
    p.add_argument("-i", "--input"); p.add_argument("-o", "--output")
    p.add_argument("--model", default="all-MiniLM-L6-v2")
    p.add_argument("--normalize", action="store_true")
    p.set_defaults(func=cmd_embed_text)

    p = sub.add_parser("embed-image", help=COMMANDS["embed-image"])
    p.add_argument("input"); p.add_argument("-o", "--output")
    p.add_argument("--model", default="ViT-B-32")
    p.add_argument("--pretrained", default="laion2b_s34b_b79k")
    p.add_argument("--normalize", action="store_true")
    p.set_defaults(func=cmd_embed_image)

    p = sub.add_parser("tokenize", help=COMMANDS["tokenize"])
    p.add_argument("text", nargs="?")
    p.add_argument("-i", "--input")
    p.add_argument("--encoding", default="cl100k_base")
    p.add_argument("--show-tokens", action="store_true")
    p.set_defaults(func=cmd_tokenize)

    p = sub.add_parser("gpt-token-count", help=COMMANDS["gpt-token-count"])
    p.add_argument("text", nargs="?")
    p.add_argument("-i", "--input")
    p.add_argument("--encoding", choices=["o200k_base", "cl100k_base", "p50k_base", "r50k_base"], default="o200k_base")
    p.set_defaults(func=cmd_gpt_token_count)

    p = sub.add_parser("vector-similarity", help=COMMANDS["vector-similarity"])
    p.add_argument("a"); p.add_argument("b")
    p.set_defaults(func=cmd_vector_similarity)

    p = sub.add_parser("vector-search", help=COMMANDS["vector-search"])
    p.add_argument("query"); p.add_argument("index")
    p.add_argument("--top-k", type=int, default=10)
    p.set_defaults(func=cmd_vector_search)

    return parser


@tool_main("ml")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
