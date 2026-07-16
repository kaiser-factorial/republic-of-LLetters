const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const dormitory = path.resolve(__dirname, '..');

function readRoomAgents() {
  return fs.readdirSync(path.join(dormitory, 'rooms'), { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function extractBlurbSlots(hallwayHtml) {
  const slots = new Map();
  const pattern = /<p data-room-blurb="([a-z]+)">([\s\S]*?)<\/p>/g;
  let match;
  while ((match = pattern.exec(hallwayHtml)) !== null) slots.set(match[1], match[2].trim());
  return slots;
}

function extractMetaDescription(roomHtml) {
  const match = roomHtml.match(/<meta\s+name="description"\s+content="([^"]*)"/);
  return match ? match[1].trim() : null;
}

const hallwayHtml = fs.readFileSync(path.join(dormitory, 'index.html'), 'utf8');
const agents = readRoomAgents();
const blurbSlots = extractBlurbSlots(hallwayHtml);

assert.deepEqual(
  [...blurbSlots.keys()].sort(),
  agents,
  'hallway data-room-blurb slots must exactly match the agents under rooms/'
);

for (const agent of agents) {
  const fallbackText = blurbSlots.get(agent);
  assert.ok(fallbackText && fallbackText.length > 0, `${agent}: hallway fallback blurb is empty`);

  const roomHtml = fs.readFileSync(path.join(dormitory, 'rooms', agent, 'index.html'), 'utf8');
  const description = extractMetaDescription(roomHtml);
  assert.ok(
    description && description.length > 0,
    `${agent}: rooms/${agent}/index.html is missing a non-empty <meta name="description"> — ` +
    'hallway-cards.js has nothing to fetch for this room'
  );
}

assert.ok(
  hallwayHtml.includes('<script src="hallway-cards.js"></script>'),
  'index.html must load hallway-cards.js so hallway blurbs sync from room meta descriptions'
);

assert.ok(
  fs.existsSync(path.join(dormitory, 'hallway-cards.js')),
  'hallway-cards.js referenced by index.html does not exist'
);

console.log('Hallway blurb sync (meta description -> hallway card) passed');
