require('http')
  .createServer((req, res) => res.end('ok'))
  .listen(process.env.PORT || 8080);
