$ErrorActionPreference = "Stop"

$pod = kubectl get pods -n registration-login-staging -l app=registration-login -o jsonpath="{.items[0].metadata.name}"
if (-not $pod) {
  throw "No registration-login pod is running."
}

$username = "smoke$(Get-Date -Format 'yyyyMMddHHmmss')"
$email = "$username@example.com"
$script = @"
const http = require('http');
const post = (path, body) => new Promise((resolve, reject) => {
  const data = JSON.stringify(body);
  const request = http.request({
    hostname: '127.0.0.1',
    port: 3000,
    path,
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data)}
  }, response => {
    let text = '';
    response.on('data', chunk => text += chunk);
    response.on('end', () => resolve({status: response.statusCode, body: text}));
  });
  request.on('error', reject);
  request.write(data);
  request.end();
});
(async () => {
  const registered = await post('/api/register', {
    username: '$username',
    email: '$email',
    password: 'SmokeTest123!',
    confirmPassword: 'SmokeTest123!'
  });
  if (registered.status !== 200 || !JSON.parse(registered.body).success) {
    throw new Error('registration failed: ' + registered.status + ' ' + registered.body);
  }
  const loggedIn = await post('/api/login', {
    username: '$username',
    password: 'SmokeTest123!'
  });
  if (loggedIn.status !== 200 || !JSON.parse(loggedIn.body).success) {
    throw new Error('login failed: ' + loggedIn.status + ' ' + loggedIn.body);
  }
  console.log('registration=200 login=200');
})().catch(error => { console.error(error.message); process.exit(1); });
"@

kubectl exec -n registration-login-staging $pod -- node -e $script
