export type TelegramMode = 'bot' | 'user';

export type Channel = {
  id: number;
  title: string;
  telegram_chat_id: string;
  mode: TelegramMode;
  active: boolean;
  created_at: string;
};

export type Article = {
  id: number;
  title: string;
  summary?: string;
  url: string;
  source: string;
  created_at: string;
};

export type PostJob = {
  id: number;
  channel_id: number;
  article_id: number;
  post_content: string;
  status: 'pending' | 'sent' | 'failed';
  tries: number;
  created_at: string;
};
