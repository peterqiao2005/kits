#!/bin/bash
set -e

echo "[INFO] 当前每个 CPU core 的频率"
for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
  cur=$(cat $cpu/cpufreq/scaling_cur_freq)
  max=$(cat $cpu/cpufreq/scaling_max_freq)
  echo "$cpu: $((cur/1000)) MHz / $((max/1000)) MHz"
done

echo "[INFO] 锁定每个 CPU core 的频率为其最大值"

for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
  max=$(cat $cpu/cpufreq/cpuinfo_max_freq)
  echo $max | sudo tee $cpu/cpufreq/scaling_min_freq > /dev/null
  echo $max | sudo tee $cpu/cpufreq/scaling_max_freq > /dev/null
done

echo "[INFO] 配置后每个 CPU core 的频率"
for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
  cur=$(cat $cpu/cpufreq/scaling_cur_freq)
  max=$(cat $cpu/cpufreq/scaling_max_freq)
  echo "$cpu: $((cur/1000)) MHz / $((max/1000)) MHz"
done


echo "[OK] 全部核心频率已锁定到各自 max"
