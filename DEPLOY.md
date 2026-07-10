# Deploying this directory as a standalone school-facing repo

Schools should clone a repo that contains **only** `worker_agent/` — never
the central-plane code. Two supported paths:

## Option A: publish as its own repo (recommended)

Push this subtree to `git@github.com:hcis-lab/aicapstone-worker.git` (or
whatever org you use). Rebuild whenever this directory changes.

```bash
# from the central repo root
git subtree split --prefix=worker_agent -b aicapstone-worker
git push git@github.com:hcis-lab/aicapstone-worker.git aicapstone-worker:main
git branch -D aicapstone-worker      # clean up local temp branch
```

Schools then run:

```bash
git clone https://github.com/hcis-lab/aicapstone-worker.git
cd aicapstone-worker
./setup.sh
```

Automate with a Makefile target if you release often:

```makefile
publish-worker:
	git subtree split --prefix=worker_agent -b _worker-split
	git push -f git@github.com:hcis-lab/aicapstone-worker.git _worker-split:main
	git branch -D _worker-split
```

## Option B: sparse-checkout of the central repo

If you don't want a second repo, schools can clone the central repo but
only pull `worker_agent/`:

```bash
git clone --filter=blob:none --sparse https://github.com/hcis-lab/aicapstone-leaderboard.git
cd aicapstone-leaderboard
git sparse-checkout set worker_agent
cd worker_agent
./setup.sh
```

Downsides: they still see the file list of the whole central repo (`git
ls-tree`), and they have to know the sparse-checkout dance. Prefer A.

## Option C: tarball release (offline installs)

For schools behind firewalls that can't reach GitHub:

```bash
tar czf aicapstone-worker-$(date +%Y%m%d).tgz -C worker_agent \
  --exclude='__pycache__' --exclude='.env' .
```

Ship the tarball. School operator:

```bash
mkdir aicapstone-worker && tar xzf aicapstone-worker-*.tgz -C aicapstone-worker
cd aicapstone-worker
./setup.sh
```
