import {registerBugReporter} from './bug-report.js';

registerBugReporter({
  mount:'[data-family-report-nav]',
  endpoint:'https://ethans-macbook-pro-2.tail8d1ac5.ts.net:8444/api/photosite/bug-reports',
  connectionHint:'Connect Tailscale and retry.',
  screenText:() => document.body.innerText,
  snapshot:() => {
    const visible = [...document.querySelectorAll('img')].map(image => {
      const rect = image.getBoundingClientRect();
      const width = Math.max(0, Math.min(innerWidth, rect.right) - Math.max(0, rect.left));
      const height = Math.max(0, Math.min(innerHeight, rect.bottom) - Math.max(0, rect.top));
      return {image, rect, area:width*height};
    }).filter(item => item.area > 0).sort((a,b) => b.area-a.area);
    return {
      source:'templates/head.html; content/static/family-reports/photosite-report.js',
      gallery:location.pathname.split('/').filter(Boolean)[0] || 'home',
      anchor:location.hash,
      scroll:{x:scrollX,y:scrollY},
      visiblePhotos:visible.slice(0,16).map(({image,rect}) => ({
        path:new URL(image.currentSrc || image.src, location.href).pathname,
        id:image.closest('.swipeable')?.id,
        link:image.closest('a')?.getAttribute('href'),
        loaded:image.complete && image.naturalWidth > 0,
        naturalSize:{width:image.naturalWidth,height:image.naturalHeight},
        displaySize:{width:Math.round(rect.width),height:Math.round(rect.height)}
      }))
    };
  }
});
