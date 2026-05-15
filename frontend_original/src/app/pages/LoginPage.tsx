import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Card } from '../components/Card';
import { Input } from '../components/Input';
import { Button } from '../components/Button';

export function LoginPage() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-gray-100 flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-2xl text-gray-900 mb-2">사내 지식 AI 검색 시스템</h1>
          <p className="text-sm text-gray-600">로그인하여 시작하세요</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="아이디"
            type="text"
            placeholder="아이디를 입력하세요"
            value={formData.username}
            onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            required
          />

          <Input
            label="비밀번호"
            type="password"
            placeholder="비밀번호를 입력하세요"
            value={formData.password}
            onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            required
          />

          <Button type="submit" variant="primary" className="w-full">
            로그인
          </Button>
        </form>

        <div className="mt-6 flex flex-col gap-2 text-center text-sm">
          <Link to="/register" className="text-blue-600 hover:text-blue-700 hover:underline">
            회원가입 신청
          </Link>
          <Link to="/change-password" className="text-gray-600 hover:text-gray-700 hover:underline">
            비밀번호 변경
          </Link>
        </div>
      </Card>
    </div>
  );
}
