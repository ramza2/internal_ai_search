import React from 'react';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  hover?: boolean;
}

export function Card({ children, className = '', padding = 'md', hover = false }: CardProps) {
  const paddingStyles = {
    none: '',
    sm: 'p-4',
    md: 'p-6',
    lg: 'p-8'
  };

  return (
    <div className={`bg-white rounded-lg border border-gray-200 shadow-sm
      ${paddingStyles[padding]}
      ${hover ? 'hover:shadow-md transition-shadow duration-200' : ''}
      ${className}`}>
      {children}
    </div>
  );
}
