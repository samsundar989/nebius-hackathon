#!/usr/bin/env bash
# gpac #4006: the three checks gpac's AGENTS.md / gpac-patching skill ask for, on unpatched and
# patched trees side by side (review #20 order 2). Runs inside leakproof/cpp-sanitizers:zlib with
# the case directory mounted at /case:
#   /case/src        upstream gpac (d958f94), unmodified
#   /case/testsuite  gpac/testsuite (shallow clone)
#   /case/4006       PoC, DRM config, the fix (H3w2.diff) and the regression test
# Writes logs to /case/4006/validation/. Never touches /case/src.
set -euo pipefail

out=/case/4006/validation
mkdir -p "$out"
rm -f "$out"/*.log "$out"/RESULTS.txt
scripts="scripts/item.sh scripts/heif.sh scripts/items_pids.sh scripts/iff_crypt.sh scripts/encryption.sh scripts/decryption_selkey.sh"
log() { echo "$*" | tee -a "$out/RESULTS.txt"; }

log "gpac #4006 validation, $(date -u +%FT%TZ)"
log "upstream: $(git -C /case/src rev-parse HEAD 2>/dev/null || echo d958f94)"
log "testsuite: $(git -C /case/testsuite rev-parse HEAD 2>/dev/null || echo unknown)"
log "compiler: $(gcc --version | head -1)"
export TERM=dumb

build() {  # build <name> <apply-fix: 0|1>
	local d=/w/$1
	rm -rf "$d"; mkdir -p /w
	mkdir -p "$d"; tar -C /case/src --exclude=.git -cf - . | tar -C "$d" -xf -
	cd "$d"
	grep -rlI '^#!' . | xargs -r chmod +x
	cp /case/4006/ut_meta_item_memory.c src/isomedia/unittests/
	if [ "$2" = 1 ]; then patch -p1 < /case/4006/H3w2.diff; fi
	# gpac's own sanitizer build with its default compiler (gcc): ASan + UBSan, no recovery.
	# (clang 18 adds -fsanitize=function, which aborts on an existing callback cast in
	# MP4Box's argument parser, unrelated to this bug.)
	./configure --enable-sanitizer --unittests > "$out/$1.configure.log" 2>&1
	# The main build without the unit tests (`all` runs them first and stops on a failure);
	# `make unit_tests` runs them below.
	set +e
	make -j"$(nproc)" UNIT_TESTS=no > "$out/$1.make.log" 2>&1
	echo $? > "/w/$1.make.rc"
	set -e
}

unit() {  # unit <name>: the full unit-test binary, then the new test alone
	cd /w/$1
	set +e
	make -j"$(nproc)" unit_tests > "$out/$1.unittests.log" 2>&1
	local rc=$?
	set -e
	log "[$1] unit tests: exit $rc"
	grep -iE "meta_item_memory|AddressSanitizer|SUMMARY|failed|passed|tests? run" "$out/$1.unittests.log" | head -12 | sed "s/^/[$1]   /" | tee -a "$out/RESULTS.txt" >/dev/null
}

repro() {  # repro <name>: the issue's command (the unit test covers a valid round trip)
	cd /w/$1
	export LD_LIBRARY_PATH=/w/$1/bin/gcc
	cp /case/4006/poc.mp4 /tmp/poc.mp4
	cp /case/4006/drm_ctr.xml /tmp/drm_ctr.xml
	set +e
	./bin/gcc/MP4Box -decrypt /tmp/drm_ctr.xml /tmp/poc.mp4 -out /tmp/out_$1.mp4 > "$out/$1.repro.log" 2>&1
	local rc=$?
	set -e
	if grep -q "AddressSanitizer" "$out/$1.repro.log"; then
		log "[$1] issue command: exit $rc, $(grep -m1 -o 'AddressSanitizer: [a-z-]*' "$out/$1.repro.log") in $(grep -m1 -oE '#[0-9]+ 0x[0-9a-f]+ in [A-Za-z_]+' "$out/$1.repro.log" | awk '{print $4}')"
	else
		log "[$1] issue command: exit $rc, no sanitizer report"
	fi
	unset LD_LIBRARY_PATH
}

suite() {  # suite <name>: the affected testsuite scripts against this build
	rm -rf /w/ts_$1; cp -a /case/testsuite /w/ts_$1
	cd /w/ts_$1
	export PATH=/w/$1/bin/gcc:$PATH LD_LIBRARY_PATH=/w/$1/bin/gcc
	# gpac under ASan: leaks are not test failures here (gpac's own CI runs the suite without LSan).
	export ASAN_OPTIONS=detect_leaks=0
	set +e
	./make_tests.sh -re -p=0 -timeout=120 $scripts > "$out/$1.testsuite.log" 2>&1
	local rc=$?
	set -e
	unset ASAN_OPTIONS
	export PATH=${PATH#/w/$1/bin/gcc:}; unset LD_LIBRARY_PATH
	log "[$1] testsuite ($scripts): exit $rc"
	grep -iE "tests? (passed|failed|executed|OK)|Total|Failed|executed|success|subtests" "$out/$1.testsuite.log" | tail -8 | sed "s/^/[$1]   /" | tee -a "$out/RESULTS.txt" >/dev/null
	ls logs 2>/dev/null > /dev/null && find . -name "*-failed*" -o -name "*.failed" 2>/dev/null | head -20 > "$out/$1.testsuite.failed.txt" || true
	cp -a results "$out/$1.testsuite.results" 2>/dev/null || true
}

for v in unpatched:0 patched:1; do
	name=${v%%:*}; fix=${v##*:}
	build "$name" "$fix"
	log "[$name] build: make exit $(cat /w/$name.make.rc)"
	unit "$name"
	repro "$name"
	suite "$name"
done
log "done $(date -u +%FT%TZ)"
