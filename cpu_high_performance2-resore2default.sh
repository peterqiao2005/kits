#!/bin/bash
set -e

echo "[INFO] 恢复每个 CPU core 的默认频率调节范围"

for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
  min=$(cat $cpu/cpufreq/cpuinfo_min_freq)
  max=$(cat $cpu/cpufreq/cpuinfo_max_freq)
  echo $min | sudo tee $cpu/cpufreq/scaling_min_freq > /dev/null
  echo $max | sudo tee $cpu/cpufreq/scaling_max_freq > /dev/null
done

for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
  cur=$(cat $cpu/cpufreq/scaling_cur_freq)
  max=$(cat $cpu/cpufreq/scaling_max_freq)
  echo "$cpu: $((cur/1000)) MHz / $((max/1000)) MHz"
done


echo "[OK] 所有核心频率已还原为自动调节范围"
