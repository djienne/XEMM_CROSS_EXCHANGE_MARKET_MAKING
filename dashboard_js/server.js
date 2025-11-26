const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const csv = require('csv-parser');

const app = express();
const PORT = 3000;

app.use(cors());
app.use(bodyParser.json());
app.use(express.static(path.join(__dirname, 'public')));

// Configuration
const BASE_DIR = path.resolve(__dirname, '..');
const REMOTE_USER = "ubuntu";
const REMOTE_HOST = "54.95.246.213";
const REMOTE_PATH = "/home/ubuntu/XEMM_rust";
const SSH_KEY_NAME = "lighter.pem";
const SSH_KEY_PATH = path.join(BASE_DIR, SSH_KEY_NAME);

// Helper to run shell commands
function runCommand(command, cwd = BASE_DIR) {
    return new Promise((resolve, reject) => {
        console.log(`Executing: ${command}`);
        exec(command, { cwd: cwd, maxBuffer: 1024 * 1024 * 10, timeout: 30000 }, (error, stdout, stderr) => {
            if (error) {
                console.warn(`Command failed: ${error.message}`);
                resolve({ success: false, stdout: stdout, stderr: stderr || error.message });
            } else {
                resolve({ success: true, stdout: stdout, stderr: stderr });
            }
        });
    });
}

function getSshCommand(remoteCmd) {
    return `ssh -i "${SSH_KEY_PATH}" -o StrictHostKeyChecking=no ${REMOTE_USER}@${REMOTE_HOST} "${remoteCmd}"`;
}

// Helper to fix line endings on remote shell scripts
async function fixRemoteLineEndings() {
    // Use find to recursively fix all .sh files, with proper escaping for SSH
    const fixCmd = `cd ${REMOTE_PATH} && find . -type f -name '*.sh' -exec sed -i 's/\\r$//' {} \\;`;
    const result = await runCommand(getSshCommand(fixCmd));
    console.log('Fixed line endings on remote .sh files:', result.success ? 'SUCCESS' : 'FAILED');
    return result;
}

// API Routes

// Get Status
app.get('/api/status', async (req, res) => {
    // Check for xemm_rust process, excluding zombie/defunct processes
    // Use ps to check actual process state, filtering out zombie (Z) and defunct (D) states
    const cmd = getSshCommand("ps aux | grep '[x]emm_rust' | grep -v grep | awk '{print $8}' | grep -E '^[^ZD]' || true");
    const result = await runCommand(cmd);

    let status = "UNKNOWN";
    if (result.success) {
        const output = result.stdout.trim();
        // If we found process states that are not zombie/defunct, the bot is running
        if (output && output.length > 0) {
            status = "RUNNING";
        } else {
            status = "STOPPED";
        }
    }

    res.json({ status, details: result });
});

// Deploy
app.post('/api/deploy', async (req, res) => {
    const cmd = `python deploy.py`;
    const result = await runCommand(cmd);

    // Fix line endings on all .sh scripts after deploy
    await fixRemoteLineEndings();

    res.json(result);
});

// Start Bot
app.post('/api/start', async (req, res) => {
    // Fix line endings on all .sh scripts before running
    await fixRemoteLineEndings();

    const cmd = `python run_remote.py`;
    const result = await runCommand(cmd);
    res.json(result);
});

// Stop Bot
app.post('/api/stop', async (req, res) => {
    // Fix line endings on all .sh scripts before running
    await fixRemoteLineEndings();

    const remoteCmd = `cd ${REMOTE_PATH} && bash kill_process.sh`;
    const cmd = getSshCommand(remoteCmd);
    const result = await runCommand(cmd);
    res.json(result);
});

// Get Logs
app.get('/api/logs', async (req, res) => {
    const lines = req.query.lines || 100;
    const cmd = getSshCommand(`tail -n ${lines} ${REMOTE_PATH}/output.log`);
    const result = await runCommand(cmd);
    res.json(result);
});

// Sync Trades (Download)
app.post('/api/sync_trades', async (req, res) => {
    const cmd = `python download_trades.py`;
    const result = await runCommand(cmd);
    res.json(result);
});

// Get Config
app.get('/api/config', (req, res) => {
    const configPath = path.join(BASE_DIR, 'config.json');
    try {
        if (fs.existsSync(configPath)) {
            const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            res.json(config);
        } else {
            res.status(404).json({ error: 'config.json not found' });
        }
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

// Get Trades (Read Local CSVs)
app.get('/api/trades', async (req, res) => {
    const tradesDir = path.join(BASE_DIR, "downloaded_trades");

    if (!fs.existsSync(tradesDir)) {
        return res.json({ trades: [] });
    }

    const files = fs.readdirSync(tradesDir).filter(f => f.endsWith('.csv'));
    const allTrades = [];

    const readPromises = files.map(file => {
        return new Promise((resolve) => {
            const results = [];
            fs.createReadStream(path.join(tradesDir, file))
                .pipe(csv())
                .on('data', (data) => {
                    if (data.timestamp !== 'timestamp') {
                        results.push(data);
                    }
                })
                .on('end', () => {
                    resolve(results);
                })
                .on('error', () => {
                    resolve([]);
                });
        });
    });

    try {
        const results = await Promise.all(readPromises);
        results.forEach(trades => allTrades.push(...trades));

        allTrades.sort((a, b) => {
            return (b.timestamp || '').localeCompare(a.timestamp || '');
        });

        res.json({ trades: allTrades.slice(0, 1000) });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log(`SSH Key Path: ${SSH_KEY_PATH}`);
});
