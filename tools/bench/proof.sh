#!/usr/bin/env bash
# Bench proof for erpcm's TT99 actions on a throwaway Frappe 16.56 / ERPNext 16.55 / Frappe HR bench.
#
#   tools/bench/proof.sh            build the bench, run every step, print the evidence, remove the bench
#   KEEP=1 tools/bench/proof.sh     leave the bench running afterwards
#   HRMS=0 tools/bench/proof.sh     without Frappe HR at first; it is installed at the end, after the
#                                   companies, to prove the way out documented for that case
#
# Needs docker and network access to Docker Hub (the mariadb, redis and frappe/erpnext images), PyPI (the
# Python dependencies of Frappe HR) and github.com (Frappe HR, cloned at a pinned tag and commit). The compose project
# is always named erpcm-thu (-p, whatever COMPOSE_PROJECT_NAME says). If containers of that project exist
# that this script did not build (no erpcm.proof=1 label), it stops; REPLACE_FOREIGN_PROJECT=1 removes
# them anyway. Installs erpcm from this working tree (copied into the container, pip install -e,
# apps.txt), not from GitHub. Lines starting with "R " are the evidence; any "R FAIL" or traceback makes
# the run exit 1. docs/ROADMAP.md records a run.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
PROJECT=erpcm-thu
HRMS_VERSION=v16.54.1
HRMS_COMMIT=a01032350ba1b799345b862cb122fa408bf6780e
# Every "R ok" the run must print, per mode: a check that silently stops running fails the proof too.
EXPECTED_HRMS=93
EXPECTED_NOHRMS=89
DC=(docker compose -p "$PROJECT" -f "$HERE/compose.yaml")
BENCH=/home/frappe/frappe-bench
LOG="$(mktemp)"
exec > >(tee "$LOG") 2>&1
in_bench() { "${DC[@]}" exec -T bench bash -lc "cd $BENCH && $*"; }
run() {
	"${DC[@]}" cp "$HERE/proof.py" bench:$BENCH/sites/proof.py >/dev/null 2>&1
	in_bench "cd sites && ../env/bin/python proof.py $*" 2>&1 | grep -E '^R |^refusing|Error|Traceback' | cut -c1-600
}
worker() { in_bench "timeout 300 bench worker --queue long,default,short --burst" 2>&1 | grep -cE 'Job OK' | sed 's/^/R background jobs run: /'; }
isolation() {
	"${DC[@]}" exec -T db mariadb -uroot -pchi-de-thu-cuc-bo -e "SET GLOBAL innodb_snapshot_isolation = $1" \
		&& echo "R innodb_snapshot_isolation set globally to $1"
}
step() { echo; echo "=== $*"; }

foreign=$(docker ps -a --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Label "erpcm.proof"}}' | grep -vc '^1$')
if [ "$foreign" -gt 0 ] && [ "${REPLACE_FOREIGN_PROJECT:-}" != 1 ]; then
	echo "refusing: docker project $PROJECT has $foreign container(s) this script did not build; set REPLACE_FOREIGN_PROJECT=1 to remove them" >&2
	exit 2
fi
"${DC[@]}" down -v >/dev/null 2>&1

step "bench and site"
"${DC[@]}" up -d 2>&1 | tail -1
in_bench "ls -1 apps > sites/apps.txt && bench set-config -g db_host db && bench set-config -gp db_port 3306 \
	&& bench set-config -g redis_cache redis://redis:6379 && bench set-config -g redis_queue redis://redis:6379 \
	&& bench set-config -g redis_socketio redis://redis:6379" >/dev/null
in_bench "bench new-site t.local --mariadb-user-host-login-scope=% --admin-password admin --db-root-username root \
	--db-root-password chi-de-thu-cuc-bo --install-app erpnext" 2>&1 | grep -E 'Scheduler|Error' | tail -1
in_bench "bench --site t.local set-config -p erpcm_proof_site 1" >/dev/null
install_hrms() {
	# Frappe HR changes what saving a Company does. Cloned and installed by hand: `bench get-app` wants yarn.
	in_bench "git clone -q --depth 1 --branch $HRMS_VERSION https://github.com/frappe/hrms apps/hrms 2>&1 | tail -1"
	got=$(in_bench "git -C apps/hrms rev-parse HEAD")
	if [ "$got" != "$HRMS_COMMIT" ]; then echo "R FAIL Frappe HR $HRMS_VERSION is commit $got, not $HRMS_COMMIT"; return; fi
	in_bench "env/bin/pip install -q -e apps/hrms && (grep -qx hrms sites/apps.txt || echo hrms >> sites/apps.txt) \
		&& bench --site t.local install-app hrms" 2>&1 | grep -E 'Error|Traceback' | tail -2
	echo "R Frappe HR $HRMS_VERSION ($got) installed"
}
[ "${HRMS:-1}" = 1 ] && install_hrms
in_bench "bench --site t.local list-apps"

step "a company created by the setup wizard (Vietnam, VND, Standard)"; run wizard
run snap "'Cong Ty Thu'" save

step "install-app erpcm from the working tree"
TMP="$(mktemp -d)"
git -C "$REPO" ls-files -co --exclude-standard -z | (cd "$REPO" && xargs -0 tar cf -) | (mkdir -p "$TMP/erpcm" && tar xf - -C "$TMP/erpcm")
"${DC[@]}" exec -T -u root bench rm -rf $BENCH/apps/erpcm
"${DC[@]}" cp "$TMP/erpcm" bench:$BENCH/apps/erpcm >/dev/null 2>&1
"${DC[@]}" exec -T -u root bench chown -R frappe:root $BENCH/apps/erpcm
rm -rf "$TMP"
in_bench "env/bin/pip install -q -e apps/erpcm && (grep -qx erpcm sites/apps.txt || echo erpcm >> sites/apps.txt) \
	&& bench --site t.local install-app erpcm" 2>&1 | grep -E 'Installing|Error' | tail -2
in_bench "bench --site t.local list-apps"
run snap "'Cong Ty Thu'" after-install

step "the wizard company keeps its chart"; run existing
step "a forced failure midway, before ERPCM has created any category, leaves nothing"
run fail error; run left-over; run fail interrupt; run left-over
step "categories compared the way the database compares names"; run collation
step "create_company: a new company with the TT99 chart, in one transaction"; run create-tt99
in_bench "bench --site t.local execute erpcm.vn.accounting.setup.chart_status --kwargs \"{'company': 'Cong Ty TT99'}\"" \
	| grep -oE '"(verdict|style)": "[^"]*"' | tr '\n' ' ' | sed 's/^/R bench execute: /'; echo
step "refused, nothing written"; run refusals
step "the write limit (max_writes_per_transaction lowered to 1500)"
in_bench "bench --site t.local set-config -p max_writes_per_transaction 1500" >/dev/null
run limit
in_bench "bench --site t.local set-config -p max_writes_per_transaction 200000" >/dev/null
step "the wizard company is untouched"; run snap "'Cong Ty Thu'" after-all
step "the TT99 company's setup compared with the wizard company's"; run setup-of
step "what one create_company writes outside the new company"; run sitewide
step "a company with no account (data import): setup_chart builds, the repairs apply"; run empty
step "HTTP"; run http
step "postings on the TT99 company"; run post
[ "${HRMS:-1}" = 1 ] && { step "Frappe HR on the TT99 company"; run hr; }
run sce; worker; run pcv; worker
step "after posting"; run after-post; run roles
step "Vietnamese-only names"; run create "'Cong Ty Ten Viet'" CTV vi
step "innodb_snapshot_isolation=OFF (the default before MariaDB 11.6.2)"
isolation OFF; run create "'Cong Ty Tat Co Lap'" CTC vi_en show; isolation ON

if [ "${HRMS:-1}" != 1 ]; then
	step "Frappe HR installed after the companies exist"; install_hrms; run hr-after
fi

step "versions"; in_bench "bench --site t.local list-apps"
[ "${KEEP:-}" = 1 ] || "${DC[@]}" down -v 2>&1 | tail -1
fails=$(grep -cE '^R FAIL|Traceback' "$LOG")
oks=$(grep -cE '^R ok' "$LOG")
if [ "${HRMS:-1}" = 1 ]; then expected=$EXPECTED_HRMS; else expected=$EXPECTED_NOHRMS; fi
echo; echo "=== $oks expectations met (expected $expected), $fails failed"
rm -f "$LOG"
[ "$fails" = 0 ] && [ "$oks" = "$expected" ]
