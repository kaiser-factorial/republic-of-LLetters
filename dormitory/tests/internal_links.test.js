const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const dormitory = path.resolve(__dirname, '..');
const siteOrigin = 'https://example.invalid';
const sitePrefix = '/republic-of-LLetters/';

// room-template.html is source scaffolding whose ../../ paths become valid only
// after it is copied into rooms/<agent>/; it is not an end-user site page.
const deployedPages = [
  'index.html',
  'common/index.html',
  'inbox/index.html',
  ...fs.readdirSync(path.join(dormitory, 'rooms'), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
    .map((room) => `rooms/${room}/index.html`)
];

function staticReferences(html) {
  const references = [];
  const pattern = /\b(?:href|src)\s*=\s*(["'])(.*?)\1/gi;
  let match;
  while ((match = pattern.exec(html)) !== null) references.push(match[2]);
  return references;
}

function isLocalReference(reference) {
  return !/^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(reference);
}

function publishedUrl(relativePath) {
  const relativeUrl = relativePath === 'index.html'
    ? ''
    : relativePath.replace(/index\.html$/, '');
  return new URL(sitePrefix + relativeUrl, siteOrigin);
}

function localTarget(resolvedUrl) {
  assert.equal(resolvedUrl.origin, siteOrigin, `${resolvedUrl.href} leaves the deployment origin`);
  assert.ok(
    resolvedUrl.pathname.startsWith(sitePrefix),
    `${resolvedUrl.href} escapes the GitHub Pages project path`
  );

  let relativeTarget = decodeURIComponent(resolvedUrl.pathname.slice(sitePrefix.length));
  if (!relativeTarget || relativeTarget.endsWith('/')) relativeTarget += 'index.html';
  const target = path.resolve(dormitory, relativeTarget);
  assert.ok(target.startsWith(`${dormitory}${path.sep}`), `${resolvedUrl.href} escapes the artifact`);
  return target;
}

function verifyReferences(page, pageUrl) {
  const html = fs.readFileSync(path.join(dormitory, page), 'utf8');
  for (const reference of staticReferences(html).filter(isLocalReference)) {
    const resolvedUrl = new URL(reference, pageUrl);
    const target = localTarget(resolvedUrl);
    assert.ok(
      fs.existsSync(target),
      `${page}: ${reference} resolves to missing artifact path ${resolvedUrl.pathname}`
    );
  }
}

for (const page of deployedPages) verifyReferences(page, publishedUrl(page));

// GitHub Pages renders 404.html at the requested URL, not /404.html. Check
// more than one depth so relative links cannot accidentally depend on the miss.
for (const missingPath of ['missing/', 'rooms/missing/deep/']) {
  verifyReferences('404.html', new URL(sitePrefix + missingPath, siteOrigin));
}

console.log('Internal dormitory links passed');
