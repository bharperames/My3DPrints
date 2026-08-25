PORT := 8742
PID  := .serve.pid

.PHONY: serve stop open log

serve: stop
	@nohup python3 serve.py > .serve.log 2>&1 & echo $$! > $(PID)
	@sleep 1
	@echo "Fidget Shelf -> http://localhost:$(PORT)   (make stop to end, make log to tail)"

stop:
	@[ -f $(PID) ] && kill `cat $(PID)` 2>/dev/null; rm -f $(PID)
	@/usr/sbin/lsof -ti tcp:$(PORT) | xargs kill 2>/dev/null; true

open:
	open http://localhost:$(PORT)

log:
	tail -f .serve.log

PY := $(HOME)/.claude/skills/3d-print-check/.venv/bin/python

.PHONY: build
build:
	cd tools && $(PY) build_designs.py && $(PY) extract_meta.py && $(PY) make_glbs.py && $(PY) build_local.py
