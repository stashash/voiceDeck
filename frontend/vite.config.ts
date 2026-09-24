import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
// Сервис designer (8090) отдаёт CORS только на origin приложения (8088): в dev-режиме, где фронтенд
// живёт на отдельном порту vite, proxy пробрасывает те же пути тем же способом, что /api и /ws —
// запрос уходит с сервера vite, а не из браузера, поэтому CORS designer не мешает.
const designer='http://localhost:8090';
export default defineConfig({plugins:[react()],server:{proxy:{
 '/api':'http://localhost:8088','/health':'http://localhost:8088','/ws':{target:'ws://localhost:8088',ws:true},
 '/design-systems':designer,'/decks':designer,'/agents':designer,'/settings/agents':designer,
}}});
