# Installing & pulling on a mainland-China network

On a mainland-China connection, a lot of "just install it" paths fail or time out. Recognize the
signature fast and switch to the mirror path instead of retrying.

## What fails direct (and how it looks)

| Target | Typical failure |
|---|---|
| Docker Hub (`registry-1.docker.io`, `auth.docker.io`) | `EOF`, `TLS handshake timeout` on `docker pull` |
| `winget` source | `安全频道支持出错` / error `0x8a15000f` |
| `wsl --install` (online) | download hangs / never completes |
| `deb.debian.org` (apt in a build) | `502 Bad Gateway` |
| HuggingFace large weights | 302-redirects to `huggingface.co` → `xethub.hf.co` (blocked); `huggingface_hub` throws `FileMetadataError: Distant resource does not seem to be on huggingface.co` |

## What connects direct (don't over-engineer these)

`desktop.docker.com` (Docker Desktop installer), GitHub release downloads, Azure blob storage.
So: get the Docker Desktop installer and the WSL MSI direct; mirror everything that goes through
package registries.

## The working mirror paths

### Docker image pulls — registry mirrors
Add to `%USERPROFILE%\.docker\daemon.json` (or Docker Desktop → Settings → Docker Engine), then
`docker desktop restart`:

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run",
    "https://docker.1panel.live",
    "https://hub.rat.dev"
  ]
}
```
(Mirror availability drifts over time — if one 404s/times out, drop it and try another. The list
above worked as of mid-2026.)

### WSL2 — offline MSI, not `wsl --install`
The online installer download hangs. Instead grab the standalone MSI from WSL's GitHub releases
(`wsl.<version>.x64.msi`) and install it offline. Prerequisite: the **VirtualMachinePlatform**
Windows feature must be enabled (that part is local, no network). No reboot needed after the MSI.

### Image builds — Tsinghua mirrors for pip & apt
Inside the Dockerfile / build:

- pip: `-i https://pypi.tuna.tsinghua.edu.cn/simple`
- apt (Debian `bookworm`+ uses `debian.sources`): `sed` `deb.debian.org` → `mirrors.tuna.tsinghua.edu.cn`
  in `/etc/apt/sources.list.d/debian.sources` before `apt-get update`.

If you'd rather not commit mirror lines, edit the Dockerfile temporarily for the build and
`git checkout -- Dockerfile` afterward.

### Model weights (the nastiest one) — ModelScope, not hf-mirror
**`hf-mirror.com` does not rescue large weights.** It mirrors small files only; the big
`pytorch_model.bin` / `model.safetensors` 302-redirects back to the blocked `xethub.hf.co`, and
`huggingface_hub` then errors out.

The reliable path is **ModelScope + local-path loading**. For a sentence-transformers model like
`BAAI/bge-m3`, `curl` each required file from
`https://modelscope.cn/models/<org>/<model>/resolve/master/<file>` into a local folder:

- `config.json`, `config_sentence_transformers.json`, `modules.json`, `sentence_bert_config.json`,
  `1_Pooling/config.json`
- `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `sentencepiece.bpe.model`
- the weights: `pytorch_model.bin` (or `model.safetensors`)

Bind-mount that folder into the container (e.g. `./models/bge-m3 → /app/models/bge-m3`), point the
app at the **local path** (`EMBEDDING_MODEL=/app/models/bge-m3`), and load with
`SentenceTransformer(<path>)`. Loading from a path skips all Hub network calls.

Add `models/` to `.gitignore` (weights don't belong in git) — which means **a new machine must
re-download them**; see `deploy-workflow.md`.

## Runtime network (separate from install-time)

If the app calls blocked APIs at runtime (e.g. `api.anthropic.com`, `arxiv.org`,
`api.semanticscholar.org`), it needs a VPN/proxy running whenever it works — typically Clash in
**TUN mode** so WSL2/Docker traffic is transparently routed. If the proxy is down, those calls
fail even though the containers are healthy. Domestic endpoints (e.g. `open.feishu.cn`) connect
direct. If the app must run unattended, the proxy has to be in the autostart chain too — see
`unattended-operation.md`.
