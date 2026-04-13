(() => {
  const input = document.querySelector('[data-page-filter]');
  const count = document.querySelector('[data-result-count]');
  const rows = Array.from(document.querySelectorAll('[data-page-row]'));
  if (!input || !count || rows.length === 0) {
    return;
  }

  const update = () => {
    const keyword = input.value.trim().toLowerCase();
    let visible = 0;
    for (const row of rows) {
      const haystack = row.dataset.search || '';
      const show = keyword === '' || haystack.includes(keyword);
      row.hidden = !show;
      if (show) {
        visible += 1;
      }
    }
    count.textContent = `${visible} / ${rows.length} 件表示`;
  };

  input.addEventListener('input', update);
  update();
})();
