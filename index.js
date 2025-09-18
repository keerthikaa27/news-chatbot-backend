const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const redis = require('redis');
const { spawn } = require('child_process');
const axios = require('axios'); 
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5000;

app.use(cors());
app.use(bodyParser.json());

// Redis client
const redisClient = redis.createClient(); 
redisClient.on('error', (err) => console.log('Redis Client Error', err));

// Cache warming function
const warmCache = async () => {
  const queries = ["latest news on india", "india economy", "modi policies"];
  const warmupSessionId = "warmup-" + Date.now(); 
  console.log('Starting cache warming...');
  
  for (const query of queries) {
    try {
      await axios.post('http://localhost:5000/chat', {
        message: query,
        sessionId: warmupSessionId
      }, { timeout: 30000 }); 
      console.log(`Cache warmed for query: "${query}"`);
    } catch (err) {
      console.error(`Cache warm failed for "${query}":`, err.message);
    }
  }
  
  // Clean up warmup session
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
    console.log('Redis connected');
    // Warm cache after Redis connects
    await warmCache();
  } catch (err) {
    console.error('Redis connect error:', err);
  }
})();


app.post('/chat', async (req, res) => {
  const { sessionId, message } = req.body;

  if (!message || !sessionId) {
    return res.status(400).json({ error: 'sessionId and message are required' });
  }

  try {
    const python = spawn('python', ['chat_query.py', message.trim()], {
      cwd: __dirname,
      env: { ...process.env, GEMINI_API_KEY: process.env.GEMINI_API_KEY, CHROMA_DIR: process.env.CHROMA_DIR }
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

      // Store in Redis
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