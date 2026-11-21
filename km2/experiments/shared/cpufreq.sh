#!/usr/bin/env bash
# ============================================================================
# CPU 周波数の固定 / 解除 / 確認 (2026-11-17、ユーザ決定「やっぱり固定にする」)。
# マシン: i7-1260P (intel_pstate active)。P コア cpu0-7 = 基本 2.1 GHz / 最大 4.7 GHz、
#         E コア cpu8-15 = 基本 1.5 GHz / 最大 3.4 GHz。
#
# 使い方 (pin / unpin は root が要る):
#   bash  km2/experiments/shared/cpufreq.sh status           # 今の設定と実際の周波数を表示 (root 不要)
#   sudo bash km2/experiments/shared/cpufreq.sh pin [MHz]   # ターボを切り、各コアの下限=上限に固定
#                                                           #   MHz 省略 = 各コアの基本周波数 (P 2100 / E 1500)
#                                                           #   MHz 指定 = 全コアをその値 (各コアの基本周波数を上限に切り詰める)
#   sudo bash km2/experiments/shared/cpufreq.sh unpin       # 元に戻す (ターボ有効、powersave、下限 400 MHz・上限 = 各コア最大)
#
# 注意: 再起動すると元に戻る (永続化はしない)。温度で強制的に下がること (サーマルスロットリング) は防げない
#       ので、実験側の -times.csv の freq_ghz / temp_max_c で確かめる。
# ============================================================================
set -eu
C=/sys/devices/system/cpu
CMD=${1:-status}
MHZ=${2:-}

status() {
  echo "driver=$(cat $C/cpu0/cpufreq/scaling_driver)  intel_pstate=$(cat $C/intel_pstate/status 2>/dev/null)  no_turbo=$(cat $C/intel_pstate/no_turbo 2>/dev/null)"
  printf "%-6s %-12s %-22s %9s %9s %9s %9s\n" cpu governor epp base min max now_MHz
  for d in $C/cpu[0-9]*; do
    f=$d/cpufreq; [ -d $f ] || continue
    printf "%-6s %-12s %-22s %9s %9s %9s %9s\n" "$(basename $d)" "$(cat $f/scaling_governor)" \
      "$(cat $f/energy_performance_preference 2>/dev/null || echo -)" \
      "$(( $(cat $f/base_frequency) / 1000 ))" "$(( $(cat $f/scaling_min_freq) / 1000 ))" \
      "$(( $(cat $f/scaling_max_freq) / 1000 ))" "$(( $(cat $f/scaling_cur_freq) / 1000 ))"
  done
}

need_root() { [ "$(id -u)" = 0 ] || { echo "root が要ります: sudo bash $0 $CMD $MHZ" >&2; exit 1; }; }

case "$CMD" in
  status) status ;;
  pin)
    need_root
    echo 1 > $C/intel_pstate/no_turbo
    for d in $C/cpu[0-9]*; do
      f=$d/cpufreq; [ -d $f ] || continue
      base=$(cat $f/base_frequency)
      tgt=$base
      if [ -n "$MHZ" ]; then tgt=$(( MHZ * 1000 )); [ $tgt -gt $base ] && tgt=$base; fi
      echo performance > $f/scaling_governor
      [ -w $f/energy_performance_preference ] && echo performance > $f/energy_performance_preference || true
      # 下限を上げる前に上限を合わせる (下限 > 上限 だと書き込みが拒否されるため、順番を選ぶ)
      if [ $tgt -ge $(cat $f/scaling_max_freq) ]; then echo $tgt > $f/scaling_max_freq; echo $tgt > $f/scaling_min_freq
      else echo $tgt > $f/scaling_min_freq; echo $tgt > $f/scaling_max_freq; fi
    done
    echo "固定しました ($(date -Is))"; status ;;
  unpin)
    need_root
    for d in $C/cpu[0-9]*; do
      f=$d/cpufreq; [ -d $f ] || continue
      echo $(cat $f/cpuinfo_min_freq) > $f/scaling_min_freq
      echo $(cat $f/cpuinfo_max_freq) > $f/scaling_max_freq
      echo powersave > $f/scaling_governor
      [ -w $f/energy_performance_preference ] && echo balance_performance > $f/energy_performance_preference || true
    done
    echo 0 > $C/intel_pstate/no_turbo
    echo "解除しました ($(date -Is))"; status ;;
  *) echo "使い方: $0 status | pin [MHz] | unpin" >&2; exit 2 ;;
esac
