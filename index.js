const fs = require('fs');
const { spawn } = require('child_process');
const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const redis = require('redis');
const axios = require('axios');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5000;
const CHROMA_DIR = process.env.CHROMA_DIR || './chroma_store';


if (!fs.existsSync(CHROMA_DIR)) {
  console.log(`${CHROMA_DIR} not found. Running embed_store.py...`);
  const embed = spawn('python', ['embed_store.py'], {
    cwd: __dirname,
    env: { ...process.env, CHROMA_DIR, CSV_FILE: process.env.CSV_FILE, COLLECTION_NAME: process.env.COLLECTION_NAME, BATCH_SIZE: process.env.BATCH_SIZE, START_ROW: process.env.START_ROW }
  });

  embed.stdout.on('data', (data) => console.log(`Embed stdout: ${data}`));
  embed.stderr.on('data', (data) => console.error(`Embed stderr: ${data}`));

  embed.on('close', (code) => {
    if (code === 0) {
      console.log('Embed store built successfully.');
    } else {
      console.error(`Embed store failed with exit code ${code}`);
    }
  });
}

app.use(cors({
  origin: ['https://news-chatbot-frontend-e592.onrender.com', 'http://localhost:3000'],
  credentials: true
}));
app.use(bodyParser.json());

// Redis client
const redisClient = redis.createClient({
  url: process.env.REDIS_URL
});
redisClient.on('error', (err) => console.error('Redis Client Error', err));

const warmCache = async () => {
  const queries = ["latest news on india", "india economy"];
  const warmupSessionId = "warmup-" + Date.now();
  console.log('Starting cache warming...');

  for (const query of queries) {
    let attempts = 3;
    while (attempts > 0) {
      try {
        await axios.post('https://news-chatbot-backend-ko8e.onrender.com/chat', {
          message: query,
          sessionId: warmupSessionId
        }, { timeout: 30000 });
        console.log(`Cache warmed for query: "${query}"`);
        break;
      } catch (err) {
        console.error(`Cache warm failed for "${query}" (attempt ${4 - attempts}):`, err.message);
        attempts--;
        if (attempts === 0) {
          console.error(`Failed to warm cache for "${query}" after 3 attempts`);
        }
        await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1s before retry
      }
    }
  }

  try {
    await redisClient.del(`session:${warmupSessionId}`);
    console.log('Warmup session cleared');
  } catch (err) {
    console.error('Failed to clear warmup session:', err.message);
  }
};

(async () => {
  try {
    await redisClient.connect();
    console.log('Connected to Redis');
    await warmCache();
  } catch (err) {
    console.error('Redis connect error:', err);
  }
})();

// Routes
app.post('/chat', async (req, res) => {
  const { sessionId, message } = req.body;

  if (!message || !sessionId) {
    return res.status(400).json({ error: 'sessionId and message are required' });
  }

  try {
    const python = spawn('python', ['chat_query.py', message.trim()], {
      cwd: __dirname,
      env: { ...process.env, GEMINI_API_KEY: process.env.GEMINI_API_KEY, CHROMA_DIR, COLLECTION_NAME: process.env.COLLECTION_NAME }
    });

    let output = '';
    let errorOutput = '';

    python.stdout.on('data', (data) => {
      output += data.toString();
    });

    python.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    python.on('close', async (code) => {
      if (code !== 0) {
        console.error(`Python error (exit code ${code}):`, errorOutput);
        return res.status(500).json({ error: 'Failed to process query', details: errorOutput });
      }

      const assistantReply = output.trim();
      if (assistantReply.includes('Error:')) {
        console.error('Python script returned error:', assistantReply);
        return res.status(500).json({ error: assistantReply });
      }

      const historyKey = `session:${sessionId}`;
      await redisClient.rPush(historyKey, JSON.stringify({ user: message, bot: assistantReply }));
      await redisClient.expire(historyKey, 3600);

      res.json({ reply: assistantReply });
    });
  } catch (err) {
    console.error('Server error:', err);
    res.status(500).json({ error: 'Something went wrong', details: err.message });
  }
});

app.get('/history/:sessionId', async (req, res) => {
  const { sessionId } = req.params;
  const historyKey = `session:${sessionId}`;
  try {
    const history = await redisClient.lRange(historyKey, 0, -1);
    const parsed = history.map((item) => JSON.parse(item));
    res.json({ history: parsed });
  } catch (err) {
    console.error('History fetch error:', err);
    res.status(500).json({ error: 'Failed to fetch history' });
  }
});

app.delete('/history/:sessionId', async (req, res) => {
  const { sessionId } = req.params;
  const historyKey = `session:${sessionId}`;
  try {
    await redisClient.del(historyKey);
    res.json({ message: 'Session cleared' });
  } catch (err) {
    console.error('Session clear error:', err);
    res.status(500).json({ error: 'Failed to clear session' });
  }
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
