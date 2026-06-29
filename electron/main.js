import { app, BrowserWindow } from 'electron'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

function createWindow() {
  const win = new BrowserWindow({
    fullscreen: false,
  width: 1920,
  height: 1080,
    frame: false,
    autoHideMenuBar: true,
    backgroundColor: '#000000',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    }
  })

  // Carica la build React
  win.loadFile(path.join(__dirname, '../dist-electron/index.html'))

  // Niente menu
  win.setMenu(null)

  //win.webContents.openDevTools()
}

app.whenReady().then(() => {
  createWindow()
})

app.on('window-all-closed', () => {
  app.quit()
})