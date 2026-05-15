import React from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../components/Card';
import { Button } from '../components/Button';

export function NotFoundPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-gray-100 flex items-center justify-center p-4">
      <Card className="w-full max-w-md text-center">
        <h1 className="text-6xl text-gray-900 mb-4">404</h1>
        <h2 className="text-2xl text-gray-900 mb-2">페이지를 찾을 수 없습니다</h2>
        <p className="text-sm text-gray-600 mb-6">
          요청하신 페이지가 존재하지 않거나 이동되었습니다.
        </p>
        <Link to="/">
          <Button variant="primary">홈으로 돌아가기</Button>
        </Link>
      </Card>
    </div>
  );
}
