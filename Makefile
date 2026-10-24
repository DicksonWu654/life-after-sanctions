PYTHON ?= .venv/bin/python
.PHONY: verify build serve refresh rebuild check export
verify:
	$(PYTHON) -S -B scripts/release/verify_public.py
build: verify
	$(PYTHON) -S -B scripts/release/build_site.py
serve:
	python3 -m http.server 8731 --bind 127.0.0.1 --directory site
refresh rebuild check export:
	$(PYTHON) -S -B scripts/pipeline.py $@
