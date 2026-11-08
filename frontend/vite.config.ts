import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      // Same-origin browser requests preserve FastAPI's httpOnly login cookie.
      proxy: {
        '/api': {
          target: env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
