import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from "path"
import tailwindcss from "@tailwindcss/vite"
import fs from 'fs'
import { resolve } from 'path'

// 强制设置为生产环境
process.env.NODE_ENV = 'production'

// 动态获取入口点配置
function getMultipleEntries() {
  const templatesDir = path.resolve(__dirname, 'src/temps')
  const entries: Record<string, string> = {}
  
  // 如果temps目录存在，扫描所有HTML模板文件
  if (fs.existsSync(templatesDir)) {
    const templateFiles = fs.readdirSync(templatesDir).filter(file => 
      file.endsWith('.html')
    )
    
    templateFiles.forEach(file => {
      const name = file.replace('.html', '')
      entries[name] = resolve(templatesDir, file)
    })
  }
  
  // 如果没有模板文件，使用默认index.html
  if (Object.keys(entries).length === 0) {
    entries['main'] = resolve(__dirname, 'index.html')
  }
  
  return entries
}

// https://vite.dev/config/
export default defineConfig({
  mode: 'production',
  base: './',
  plugins: [
    react(), 
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": path.resolve("./src"),
    },
  },
  build: {
    // 生产环境构建配置
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: false,
        drop_debugger: true,
      },
    },
    sourcemap: false,
    target: 'es2020',
    cssCodeSplit: true,
    rollupOptions: {
      // 动态配置多入口点
      input: getMultipleEntries(),
      output: {
        // 为每个卡片创建独立目录
        entryFileNames: (chunkInfo) => {
          // 如果是主入口，保持原有结构
          if (chunkInfo.name === 'main') {
            return 'assets/js/[name]-[hash].js'
          }
          // 每个卡片的JS文件放在各自目录中
          return `${chunkInfo.name}/assets/js/[name]-[hash].js`
        },
        chunkFileNames: (_chunkInfo) => {
          // 共享的chunk文件，需要根据引用它的入口点来决定放在哪里
          // 这里我们放在共享的assets目录，但会在后处理中复制到各个卡片目录
          return 'shared/js/[name]-[hash].js'
        },
        assetFileNames: (assetInfo) => {
          // CSS和其他资源文件的处理
          if (assetInfo.name?.endsWith('.css')) {
            // CSS文件会在后处理中复制到各个卡片目录
            return 'shared/css/[name]-[hash][extname]'
          } else if (assetInfo.name?.endsWith('.otf')) {
            return 'shared/[name][extname]'
          }
          return 'shared/[name]-[hash][extname]'
        }
      },
      external: [],
      treeshake: true,
    },
    // 确保所有资源使用相对路径
    assetsDir: 'assets',
    outDir: 'dist',
    reportCompressedSize: false,
    chunkSizeWarningLimit: 1000,
  },
  esbuild: {
    drop: ['console', 'debugger'],
  },
  define: {
    'process.env.NODE_ENV': '"production"',
  },
})