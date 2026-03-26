module.exports = {
  apps: [
    {
      name: 'binanceAlpha-Airdrop-monitor',
      cwd: __dirname,
      script: './binanceAlpha-Airdrop-monitor.py',
      interpreter: 'python3',
      cron_restart: '*/30 * * * *',
      autorestart: false,
    },
  ],
};

