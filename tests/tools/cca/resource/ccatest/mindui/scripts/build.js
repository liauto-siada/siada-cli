#!/usr/bin/env node

/**
 * 简化的卡片构建脚本
 * 用法: node scripts/build.js CardName
 */

import fs from 'fs'
import path from 'path'
import { execSync } from 'child_process'
import { fileURLToPath } from 'url'
import archiver from 'archiver'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// 获取命令行参数
const args = process.argv.slice(2)
if (args.length === 0) {
  console.error('❌ 请指定卡片名称')
  console.error('用法: node scripts/build.js CardName')
  process.exit(1)
}

const cardName = args[0]
console.log(`🚀 开始构建卡片: ${cardName}`)

// 项目根目录
const projectRoot = path.resolve(__dirname, '..')
const indexHtmlPath = path.join(projectRoot, 'index.html')
const distDir = path.join(projectRoot, 'dist')
const packagesDir = path.join(projectRoot, 'packages')

// 生成HTML模板
const generateHtmlTemplate = (cardName) => {
  return `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>${cardName}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/cards/${cardName}.tsx"></script>
    <script>
      (function () {
        const params = new URLSearchParams(window.location.search);
        if (window.widgetBridge?.isDarkMode?.() || params.get('theme') === 'dark') {
          document.documentElement.classList.add('dark');
        } else {
          document.documentElement.classList.remove('dark');
        }
      })();
    </script>
  </body>
</html>`
}

// 验证卡片文件是否存在
const validateCard = () => {
  const cardPath = path.join(projectRoot, 'src', 'cards', `${cardName}.tsx`)
  if (!fs.existsSync(cardPath)) {
    console.error(`❌ 卡片文件不存在: src/cards/${cardName}.tsx`)
    process.exit(1)
  }
  console.log(`✅ 找到卡片文件: src/cards/${cardName}.tsx`)
}

// 创建ZIP文件
const createZipFile = () => {
  return new Promise((resolve, reject) => {
    const cardDistDir = path.join(distDir, cardName)
    const zipPath = path.join(packagesDir, `${cardName}.zip`)

    console.log(`📦 正在创建ZIP文件: ${cardName}.zip`)

    // 确保packages目录存在
    if (!fs.existsSync(packagesDir)) {
      fs.mkdirSync(packagesDir, { recursive: true })
      console.log(`✅ 创建packages目录: ${packagesDir}`)
    }

    // 如果已存在同名ZIP文件，先删除
    if (fs.existsSync(zipPath)) {
      try {
        fs.unlinkSync(zipPath)
        console.log(`🗑️ 删除已存在的ZIP文件: ${zipPath}`)
      } catch (err) {
        console.error(`❌ 删除已存在的ZIP文件失败: ${zipPath}`, err)
        // 继续尝试创建，可能会覆盖
      }
    }

    // 创建ZIP文件
    const output = fs.createWriteStream(zipPath)
    const archive = archiver('zip', {
      zlib: { level: 9 } // 最高压缩级别
    })

    output.on('close', () => {
      const sizeBytes = archive.pointer()
      const sizeKB = Math.round(sizeBytes / 1024)
      console.log(`✅ ZIP文件创建成功: ${cardName}.zip (${sizeKB}KB)`)
      
      // 验证ZIP文件是否真的存在
      if (fs.existsSync(zipPath)) {
        const stats = fs.statSync(zipPath)
        console.log(`✅ ZIP文件已验证存在，大小: ${stats.size} 字节`)
        resolve({ size: sizeBytes, sizeKB })
      } else {
        console.error(`❌ ZIP文件验证失败: ${zipPath} 不存在`)
        reject(new Error(`ZIP文件创建后验证失败: ${zipPath} 不存在`))
      }
    })

    output.on('error', (err) => {
      console.error(`❌ 创建ZIP文件输出流错误:`, err)
      reject(err)
    })

    archive.on('error', (err) => {
      console.error(`❌ 创建ZIP文件归档错误:`, err)
      reject(err)
    })

    archive.on('warning', (err) => {
      if (err.code === 'ENOENT') {
        console.warn(`⚠️ ZIP文件创建警告:`, err)
      } else {
        console.error(`❌ ZIP文件创建严重警告:`, err)
        reject(err)
      }
    })

    archive.pipe(output)

    // 添加卡片目录中的所有文件
    archive.directory(cardDistDir, false)

    // 完成归档
    archive.finalize()
  })
}

// 移动文件到卡片目录
const moveFilesToCardDir = () => {
  console.log('📁 正在重组目录结构...')

  const cardDistDir = path.join(distDir, cardName)

  // 创建卡片目录
  if (!fs.existsSync(cardDistDir)) {
    fs.mkdirSync(cardDistDir, { recursive: true })
  }

  // 获取dist目录中的所有文件和目录
  const distItems = fs.readdirSync(distDir)

  distItems.forEach(item => {
    // 跳过已经创建的cardName目录
    if (item === cardName) {
      return
    }

    const srcPath = path.join(distDir, item)
    const destPath = path.join(cardDistDir, item)

    // 移动文件或目录
    fs.renameSync(srcPath, destPath)
    console.log(`  📄 移动: ${item} -> ${cardName}/${item}`)
  })
}

// 主构建流程
const build = async () => {
  try {
    // 1. 验证卡片文件
    validateCard()

    // 2. 删除旧的index.html
    if (fs.existsSync(indexHtmlPath)) {
      fs.unlinkSync(indexHtmlPath)
      console.log('🗑️  删除旧的index.html')
    }

    // 3. 创建新的index.html
    const htmlContent = generateHtmlTemplate(cardName)
    fs.writeFileSync(indexHtmlPath, htmlContent)
    console.log('📝 创建新的index.html')

    // 4. 清理旧的构建产物
    if (fs.existsSync(distDir)) {
      fs.rmSync(distDir, { recursive: true, force: true })
      console.log('🧹 清理旧的构建产物')
    }

    // 5. 执行构建
    console.log('🔨 开始Vite构建...')
    try {
      execSync('npm run build', {
        stdio: 'inherit',
        cwd: projectRoot
      })
      console.log('✅ 构建完成')
    } catch (buildError) {
      console.error('❌ Vite构建失败:', buildError.message)
      throw new Error(`Vite构建失败: ${buildError.message}`)
    }

    // 6. 重组目录结构
    try {
      moveFilesToCardDir()
    } catch (moveError) {
      console.error('❌ 移动文件失败:', moveError.message)
      throw new Error(`移动文件失败: ${moveError.message}`)
    }

    // 7. 创建ZIP文件 - 添加重试逻辑
    let zipResult = null
    let retryCount = 0
    const maxRetries = 3
    let lastError = null

    while (retryCount < maxRetries) {
      try {
        console.log(`尝试创建ZIP文件 (${retryCount + 1}/${maxRetries})...`)
        zipResult = await createZipFile()
        // 如果成功创建了ZIP文件，跳出循环
        console.log(`✅ ZIP文件创建成功 (尝试 ${retryCount + 1}/${maxRetries})`)
        break
      } catch (zipError) {
        lastError = zipError
        retryCount++
        console.error(`❌ 创建ZIP文件失败 (尝试 ${retryCount}/${maxRetries}):`, zipError.message)
        
        if (retryCount < maxRetries) {
          // 等待一秒后重试
          console.log(`🕒 等待1秒后重试...`)
          await new Promise(resolve => setTimeout(resolve, 1000))
        }
      }
    }

    // 如果所有重试都失败了
    if (!zipResult) {
      throw new Error(`创建ZIP文件失败，已重试${maxRetries}次: ${lastError ? lastError.message : '未知错误'}`)
    }

    // 8. 生成构建报告
    const report = {
      success: true,
      timestamp: new Date().toISOString(),
      cardName,
      zipFile: `${cardName}.zip`,
      size: zipResult.size,
      sizeKB: zipResult.sizeKB
    }

    const reportPath = path.join(packagesDir, 'build-report.json')
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2))

    console.log('\n🎉 构建完成！')
    console.log(`📊 构建报告:`)
    console.log(`  • 卡片: ${cardName}`)
    console.log(`  • 大小: ${zipResult.sizeKB}KB`)
    console.log(`  • ZIP文件: ${cardName}.zip`)
    console.log(`  • 构建目录: dist/${cardName}/`)
    console.log(`\n📁 文件位置:`)
    console.log(`  • ZIP文件: ${path.relative(process.cwd(), path.join(packagesDir, `${cardName}.zip`))}`)
    console.log(`  • 构建目录: ${path.relative(process.cwd(), path.join(distDir, cardName))}`)

    // 再次验证ZIP文件是否存在
    const finalZipPath = path.join(packagesDir, `${cardName}.zip`)
    if (fs.existsSync(finalZipPath)) {
      const stats = fs.statSync(finalZipPath)
      console.log(`✅ 最终验证: ZIP文件存在，大小: ${Math.round(stats.size / 1024)}KB`)
    } else {
      console.error(`❌ 最终验证: ZIP文件不存在!`)
      throw new Error('构建完成但ZIP文件不存在')
    }

  } catch (error) {
    console.error('❌ 构建失败:', error.message)

    // 生成错误报告
    const errorReport = {
      success: false,
      timestamp: new Date().toISOString(),
      error: error.message,
      cardName
    }

    if (!fs.existsSync(packagesDir)) {
      fs.mkdirSync(packagesDir, { recursive: true })
    }

    const reportPath = path.join(packagesDir, 'build-report.json')
    fs.writeFileSync(reportPath, JSON.stringify(errorReport, null, 2))

    process.exit(1)
  }
}

// 检查Node.js版本
const checkNodeVersion = () => {
  const version = process.version
  const majorVersion = parseInt(version.slice(1).split('.')[0])

  if (majorVersion < 16) {
    console.error('❌ 需要Node.js 16或更高版本')
    process.exit(1)
  }
}

// 主入口
const main = () => {
  checkNodeVersion()
  build()
}

main() 