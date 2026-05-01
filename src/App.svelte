<script>
  import { fontawesomeManifest, iconsPerPage, pageCount } from './generated/fontawesomeManifest.js'

  // Saturated foreground colors for icon glyphs
  const iconColors = [
    { name: 'black',   primary: '#111827', secondary: '#6b7280' },
    { name: 'slate',   primary: '#334155', secondary: '#94a3b8' },
    { name: 'blue',    primary: '#2563eb', secondary: '#93c5fd' },
    { name: 'sky',     primary: '#0284c7', secondary: '#7dd3fc' },
    { name: 'teal',    primary: '#0f766e', secondary: '#5eead4' },
    { name: 'green',   primary: '#16a34a', secondary: '#86efac' },
    { name: 'lime',    primary: '#65a30d', secondary: '#bef264' },
    { name: 'amber',   primary: '#d97706', secondary: '#fcd34d' },
    { name: 'orange',  primary: '#ea580c', secondary: '#fdba74' },
    { name: 'red',     primary: '#dc2626', secondary: '#fca5a5' },
    { name: 'rose',    primary: '#e11d48', secondary: '#fda4af' },
    { name: 'pink',    primary: '#db2777', secondary: '#f9a8d4' },
    { name: 'purple',  primary: '#7c3aed', secondary: '#c4b5fd' },
    { name: 'indigo',  primary: '#4f46e5', secondary: '#a5b4fc' },
    { name: 'brown',   primary: '#92400e', secondary: '#d6a36a' },
  ]

  // Light pastel backgrounds — one per fg color slot, offset by N/3 so
  // bg index always differs from fg index. All are light enough to contrast
  // with every saturated fg color above.
  const bgColors = [
    { name: 'light rose',    color: '#ffe4e6' },
    { name: 'light lime',    color: '#ecfccb' },
    { name: 'light amber',   color: '#fef3c7' },
    { name: 'light green',   color: '#dcfce7' },
    { name: 'light pink',    color: '#fce7f3' },
    { name: 'light orange',  color: '#ffedd5' },
    { name: 'light indigo',  color: '#e0e7ff' },
    { name: 'light sky',     color: '#e0f2fe' },
    { name: 'light purple',  color: '#f3e8ff' },
    { name: 'light teal',    color: '#ccfbf1' },
    { name: 'light blue',    color: '#dbeafe' },
    { name: 'light red',     color: '#fee2e2' },
    { name: 'light slate',   color: '#f1f5f9' },
    { name: 'light gray',    color: '#f3f4f6' },
    { name: 'light yellow',  color: '#fefce8' },
  ]

  // Offset guarantees bg index != fg index for any fg index in [0, N)
  const BG_OFFSET = Math.ceil(iconColors.length / 3)

  function seededRandom(seed) {
    let s = seed >>> 0
    return () => {
      s += 0x6D2B79F5
      let v = s
      v = Math.imul(v ^ (v >>> 15), v | 1)
      v ^= v + Math.imul(v ^ (v >>> 7), v | 61)
      return ((v ^ (v >>> 14)) >>> 0) / 4294967296
    }
  }

  function getPageNumber() {
    const params = new URLSearchParams(window.location.search)
    const parsed = Number(params.get('page') || '1')
    if (!Number.isInteger(parsed) || parsed < 1) return 1
    if (parsed > pageCount) return 1
    return parsed
  }

  function computePageIcons(page) {
    const start = (page - 1) * iconsPerPage
    const slice = fontawesomeManifest.slice(start, start + iconsPerPage)
    const rng = seededRandom((page * 0x9E3779B1) ^ 0x85EBCA77)

    return slice.map((icon) => {
      const fgIndex = Math.floor(rng() * iconColors.length)
      const color = iconColors[fgIndex]
      // bg index is offset from fg index so they never map to the same slot
      const bgIndex = (fgIndex + BG_OFFSET) % bgColors.length
      const bg = bgColors[bgIndex]
      const size = Math.round(34 + rng() * 34)
      const sizeLabel = size < 45 ? 'small' : size > 56 ? 'large' : 'medium-sized'
      return { ...icon, color, bg, size, sizeLabel }
    })
  }

  function getAltId(icon) {
    return `${icon.styleName} ${icon.label}`
  }

  function getAppearanceId(icon) {
    return icon.appearanceId
  }

  function syncPage() {
    pageNumber = getPageNumber()
  }

  let pageNumber = getPageNumber()
  $: pageIcons = computePageIcons(pageNumber)
</script>

<svelte:window on:popstate={syncPage} />

<main class="icon-page">
  <section class="icon-grid">
    {#each pageIcons as icon (icon.visualKey + icon.styleName)}
      <div
        class="icon-target cursor-pointer"
        style="--icon-size: {icon.size}px; color: {icon.color.primary}; background-color: {icon.bg.color}; --fa-primary-color: {icon.color.primary}; --fa-secondary-color: {icon.color.secondary};"
        alt-id={getAltId(icon)}
        appearance-id={getAppearanceId(icon)}
        functionality-id={icon.functionalityId}
        intent-id={icon.intentId}
        data-visual-key={icon.visualKey}
        data-icon-class={icon.iconClass}
        data-style-name={icon.styleName}
      >
        <i class="fa-fw pointer-events-none {icon.styleClass} {icon.iconClass}"></i>
      </div>
    {/each}
  </section>
</main>
