import { createRoot } from 'react-dom/client';
import { Router } from './router';
// Шрифты локально (CSP сервиса запрещает fonts.googleapis.com): Onest — интерфейс, JetBrains Mono — коды и кегли,
// Play — превью шрифта загруженного шаблона на экранах дизайн-системы (docs/design/canvas/gen.py PLAY).
import '@fontsource/onest/400.css';
import '@fontsource/onest/500.css';
import '@fontsource/onest/600.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/play/400.css';
import '@fontsource/play/700.css';
import './style.css';

createRoot(document.getElementById('root')!).render(<Router/>);
