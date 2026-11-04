# Online3DViewer and model publishing

The owner requested Online3DViewer at `https://3dviewer.harm.org`, a publishing
CLI, and an agent skill on 2026-11-03. The upstream viewer runs as a static site;
existing Artifact storage owns immutable publications. No new container,
database, credentials or public write API is introduced.

| Resource | Location |
| --- | --- |
| Viewer | `https://3dviewer.harm.org` |
| Loopback origin | `http://127.0.0.1:8881` |
| User service | `3dviewer.service` (Caddy) |
| Upstream source | `~/git/Online3DViewer`, https://github.com/kovacsv/Online3DViewer |
| Site releases | `~/.local/share/3dviewer/releases/<upstream SHA>-<build recipe hash>` |
| Active site | `~/.local/share/3dviewer/current` symlink |
| Model storage | [Artifact](../artifact/README.md), unchanged |
| CLI | `~/.local/bin/3dviewer` |
| Agent skill | `~/git/skillpack/skills/3dviewer/SKILL.md` |

## Publish

```sh
3dviewer publish board.step
3dviewer publish part.stl --json
3dviewer publish ./model-export/ --entry assembly.obj --title "Assembly"
3dviewer publish scene.gltf scene.bin textures/ --json
```

Use a dedicated export folder with the model and its material/texture/buffer
sidecars. Directory paths are preserved. Multiple input directories retain their
basename; one input directory publishes its contents. Select `--entry` when the
publication contains multiple models; only that model and the sidecars enter the
viewer URL. Browser loading, orbit, measurement, export and download are upstream
features. Dropping a local file into the viewer only opens it in that browser;
the CLI creates a shareable publication.

Normal stdout is the viewer URL; file-list and ZIP URLs go to stderr. `--json`
returns `url`, `embed_url`, `model_urls`, and the complete `artifact` receipt.
Publishing is public and immutable, with no expiration. Artifact enforces its
89 MiB/1,000-file CLI limits and verifies hashes. The wrapper rejects unrelated
files, hidden paths, symlinks, URL delimiters in names and duplicate leaf names
before upload: the upstream importer identifies dependencies by leaf filename.
Keep referenced texture filenames intact; rename in the model export tool if
necessary. A ZIP may contain multiple models and trigger upstream's selector.

The viewer's `/models/ID/path` route proxies GET/HEAD requests for model and
sidecar extensions to loopback Artifact. This avoids CORS changes to Artifact.
Other model-prefix paths return 404; writes return 405. CLI uploads continue
through Artifact's existing public API. If publication succeeds but route
verification fails, the CLI reports the existing manifest URL; inspect it before
retrying, because retry creates a new snapshot.

## Build and install

`build-site` archives the clean upstream checkout, installs its locked NPM
dependencies with lifecycle scripts disabled, applies the recorded `fflate.patch`
(0.8.3 fixes [GHSA-px8p-9vwx-vf98](https://github.com/advisories/GHSA-px8p-9vwx-vf98)),
requires a clean runtime npm audit, builds the production website,
includes the MIT license and revision, and atomically publishes a complete
release. The npm esbuild platform binary is provided by its optional package.
The build adds document language, a home-link label, zoom support and readable link colors, verified with UIPass. It keeps upstream branding; canonical and embed navigation point here.
STEP/IGES/BREP, Rhino, IFC and Draco loaders retain upstream's versioned jsDelivr
dependencies. Parsing runs in the browser; model files are fetched from this
host. CDN availability is a dependency for those formats.

```sh
git clone https://github.com/kovacsv/Online3DViewer.git ~/git/Online3DViewer
./build-site
install -Dm755 3dviewer ~/.local/bin/3dviewer
install -Dm644 Caddyfile ~/.config/3dviewer/Caddyfile
install -Dm644 3dviewer.service ~/.config/systemd/user/3dviewer.service
systemctl --user daemon-reload
systemctl --user enable --now 3dviewer.service
```

Install both canonical Cloudflare ingress files as documented in
[cloudflared](../cloudflared/README.md), then restart that system unit and verify
the public hostname. Existing wildcard DNS routes to the tunnel. The new ingress
rule is hostname-specific; other services retain their routes.

Upgrades are explicit maintenance: fast-forward the clean upstream checkout,
run `build-site`, then verify a mesh, a STEP file and a textured model in a browser.
Record the source revision and results here. A repeated revision/build-recipe pair is rejected;
it never overwrites an existing release. The infra operator owns deployment and
loader incidents; upstream owns import/render behavior. Revisit this arrangement
if loader availability or upstream maintenance becomes inadequate.

## Verify and recover

```sh
curl -fsS http://127.0.0.1:8881/healthz
curl -fsS https://3dviewer.harm.org/source-revision.txt
systemctl --user is-active 3dviewer artifact
```

Keep previous releases until verification completes. Roll back the `current`
symlink to the retained release (atomic rename); Caddy serves it without restart.
To retire, stop/disable the user service and remove only this hostname from both
Cloudflare configurations. Published files remain under Artifact and retain their
download URLs. Preserve them unless deletion is explicitly authorized.

## Verification record

Deployed upstream `d025663dcdd101527e87971d9ae2cf16f02949b4` (0.19.0).
Public STL, ZIP and nested-texture OBJ CLI uploads and a STEP assembly rendered in
Chromium with no JavaScript errors or failed requests. Orbit interaction passed.
UIPass checked empty, mesh and textured states at 1280x900 and 390x844: six cases,
zero blocking findings or warnings after the accessibility fixes. All six final
screenshots were visually inspected. Infrastructure tests (54), structural
validation, runtime npm audit (zero vulnerabilities), ingress parity, service
activation and existing Plane/Artifact health checks pass.

[Working example](https://3dviewer.harm.org/#model=https://3dviewer.harm.org/models/r3huue/tetrahedron.stl).
Local evidence, screenshots, CLI receipts and the review are retained under
`~/.local/state/3dviewer-deploy-20261103/` (`review.md`, `browser-result.json`,
`uipass-4/verdict.json`). Skillpack commit `c1ee8d5` installs the `3dviewer` skill
across the configured harnesses. Published model data remains in Artifact.
