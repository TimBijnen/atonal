MPREMOTE ?= mpremote
PICO_PORT ?= /dev/ttyACM0

FIRMWARE_FILES := main.py config.py display.py hw.py logic.py menu.py sequencer.py terts.py toneclock.py

.PHONY: check-tools deploy run sim venv-new venv-activate install

check-tools:
	@command -v $(MPREMOTE) >/dev/null 2>&1 || { \
		echo "mpremote not found. Install it with:"; \
		echo "  python3 -m pip install mpremote"; \
		exit 1; \
	}

deploy: check-tools
	@echo "Deploying Pico firmware to $(PICO_PORT)"
	@for f in $(FIRMWARE_FILES); do \
		echo "  -> $$f"; \
		$(MPREMOTE) connect $(PICO_PORT) fs cp "$$f" ":/$$f"; \
	done
	@echo "Deployment complete."

run: check-tools
	@$(MPREMOTE) connect $(PICO_PORT) exec "import main; main.App().run()"

sim:
	@python3 sim/run_sim.py

venv-new:
	@python3.13 -m venv .venv

venv-activate:
	@. .venv/bin/activate 

install:
	@python3 -m pip install -r requirements_dev.txt
	@python3 -m pip install -r requirements_sim.txt
