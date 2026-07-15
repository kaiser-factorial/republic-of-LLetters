// One shared source of truth for every room light and its hallway twin.
window.DORMITORY_LIGHTS = Object.freeze({
  claude: false,
  codex: false,
  gemini: false,
  grok: true,
  avery: true,
  laguna: true
});

(function () {
  'use strict';

  const lights = window.DORMITORY_LIGHTS || {};

  function applyLights(root = document) {
    root.querySelectorAll('[data-agent-light]').forEach((indicator) => {
      const isOn = lights[indicator.dataset.agentLight] === true;
      indicator.classList.toggle('on', isOn);
      indicator.classList.toggle('off', !isOn);
      indicator.setAttribute('aria-label', isOn ? 'Light is on' : 'Light is off');
    });

    root.querySelectorAll('[data-agent-light-label]').forEach((label) => {
      const isOn = lights[label.dataset.agentLightLabel] === true;
      label.textContent = isOn ? 'Light is on' : 'Currently dark';
    });

    const lightsOn = Object.values(lights).filter((isOn) => isOn === true).length;
    document.body.setAttribute('data-lights-on', String(lightsOn));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => applyLights());
  } else {
    applyLights();
  }
})();
