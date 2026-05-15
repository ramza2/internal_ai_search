import React from 'react';
import { Search } from 'lucide-react';

interface SearchInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onSearch?: () => void;
}

export function SearchInput({ onSearch, className = '', ...props }: SearchInputProps) {
  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && onSearch) {
      onSearch();
    }
  };

  return (
    <div className={`relative ${className}`}>
      <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
      <input
        type="text"
        className="w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg
          focus:border-blue-500 focus:ring-2 focus:ring-blue-200 outline-none
          text-base transition-all duration-200"
        onKeyPress={handleKeyPress}
        {...props}
      />
    </div>
  );
}
