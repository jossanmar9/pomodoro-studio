(() => {
  const focus = document.querySelector('#focus');
  const pause = document.querySelector('#break');
  const duration = document.querySelector('#duration');
  const main = document.querySelector('#preview-main');
  const detail = document.querySelector('#preview-detail');
  if (!focus || !pause || !duration) return;

  const update = () => {
    const f = Number(focus.value) || 0;
    const b = Number(pause.value) || 0;
    const total = Number(duration.value) || 0;
    const cycle = f + b;
    const complete = cycle > 0 ? Math.floor(total / cycle) : 0;
    const hours = Math.floor(total / 60);
    const minutes = total % 60;
    const durationText = [hours ? `${hours} h` : '', minutes ? `${minutes} min` : ''].filter(Boolean).join(' ') || '0 min';
    main.textContent = `${f} min concentració · ${b} min descans`;
    detail.textContent = `${durationText} totals · ${complete} cicles complets aproximats`;
  };

  document.querySelectorAll('[data-presets] button').forEach((button) => {
    button.addEventListener('click', () => {
      focus.value = button.dataset.focus;
      pause.value = button.dataset.break;
      update();
    });
  });

  document.querySelectorAll('[data-durations] button').forEach((button) => {
    button.addEventListener('click', () => {
      duration.value = button.dataset.minutes;
      update();
    });
  });

  [focus, pause, duration].forEach((input) => input.addEventListener('input', update));
  update();
})();
