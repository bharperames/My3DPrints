PY := $(HOME)/.claude/skills/3d-print-check/.venv/bin/python
PORT := 8742
PID  := .serve.pid

.PHONY: serve stop open log

serve: stop
	@nohup $(PY) serve.py > .serve.log 2>&1 & echo $$! > $(PID)
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
	cd tools && $(PY) build_designs.py && $(PY) extract_meta.py && $(PY) previews.py && $(PY) versions.py && $(PY) build_local.py

.PHONY: test
test:
	$(PY) -m unittest discover -s tests

# Everything under models/ that can be rebuilt. The shelf (models/*.3mf and
# *.stl) and the designer photos in meta/ are never touched: those are the
# only files here that cannot be regenerated.
clean-cache:
	@echo "generated parts   $$(ls models/custom 2>/dev/null | wc -l | tr -d ' ') files  $$(du -sh models/custom 2>/dev/null | cut -f1)"
	@echo "card previews     $$(ls models/glb/prev 2>/dev/null | wc -l | tr -d ' ') files  $$(du -sh models/glb/prev 2>/dev/null | cut -f1)"
	@echo ""
	@echo "run 'make clean-cache-yes' to delete them; 'make build' rebuilds"

clean-cache-yes:
	rm -rf models/custom models/glb/prev models/previews.json
	@echo "cleared. run 'make build'"
