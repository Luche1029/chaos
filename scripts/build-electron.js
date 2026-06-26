import { execSync } from 'child_process'
import fs from 'fs'
import path from 'path'

const unityInPublic = path.join('public', 'unity')
const unityTemp = 'unity_temp'

// Ripristina se run precedente fallita
if (fs.existsSync(unityTemp) && !fs.existsSync(unityInPublic)) {
  fs.renameSync(unityTemp, unityInPublic)
}

// Sposta unity FUORI da public
if (fs.existsSync(unityInPublic)) {
  fs.renameSync(unityInPublic, unityTemp)
  console.log('✓ unity/ spostata fuori da public/')
}

try {
  execSync('npx vite build --outDir dist-electron --mode electron', { stdio: 'inherit' })
  console.log('✓ Build electron completata')
} finally {
  if (fs.existsSync(unityTemp)) {
    fs.renameSync(unityTemp, unityInPublic)
    console.log('✓ unity/ ripristinata in public/')
  }
}