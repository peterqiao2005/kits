module.exports = {
  apps: [
    {
      name: "serverroomPrice",
      script: "./serverroomPrice/dicountMonitoringNew",
      interpreter: "python3",
      cron_restart: "0 */4 * * *",   // 每 4 小时执行一次
      autorestart: false,            // 执行完就退出，不常驻
    },
  ]
};
