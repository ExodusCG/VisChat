/**
 * CC_VisChat - 认证模块
 * 处理用户登录、登出、会话管理
 */

const Auth = {
    // 当前用户信息缓存
    currentUser: null,

    /**
     * 用户登录
     * @param {string} username 用户名
     * @param {string} password 密码
     * @returns {Promise<{success: boolean, message?: string, user?: object}>}
     */
    async login(username, password) {
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ username, password }),
                credentials: 'include', // 包含 cookies
            });

            const data = await response.json();

            if (response.ok) {
                this.currentUser = data.user;
                // 存储用户基本信息到本地
                localStorage.setItem('user', JSON.stringify(data.user));
                return { success: true, user: data.user };
            } else {
                return { success: false, message: data.detail || '登录失败' };
            }
        } catch (error) {
            console.error('Login error:', error);
            return { success: false, message: '网络错误，请稍后重试' };
        }
    },

    /**
     * 用户登出
     * @returns {Promise<{success: boolean}>}
     */
    async logout() {
        try {
            const response = await fetch('/api/auth/logout', {
                method: 'POST',
                credentials: 'include',
            });

            // 清除本地存储
            this.currentUser = null;
            localStorage.removeItem('user');

            return { success: response.ok };
        } catch (error) {
            console.error('Logout error:', error);
            // 即使请求失败也清除本地状态
            this.currentUser = null;
            localStorage.removeItem('user');
            return { success: false };
        }
    },

    /**
     * 获取当前登录用户信息
     * @returns {Promise<object|null>}
     */
    async getCurrentUser() {
        // 首先检查缓存
        if (this.currentUser) {
            return this.currentUser;
        }

        // 检查本地存储
        const storedUser = localStorage.getItem('user');
        if (storedUser) {
            try {
                this.currentUser = JSON.parse(storedUser);
            } catch (e) {
                localStorage.removeItem('user');
            }
        }

        // 从服务器验证
        try {
            const response = await fetch('/api/auth/me', {
                method: 'GET',
                credentials: 'include',
            });

            if (response.ok) {
                const data = await response.json();
                this.currentUser = data;
                localStorage.setItem('user', JSON.stringify(data));
                return data;
            } else {
                // 会话无效，清除本地存储
                this.currentUser = null;
                localStorage.removeItem('user');
                return null;
            }
        } catch (error) {
            console.error('Get current user error:', error);
            return null;
        }
    },

    /**
     * 检查是否已登录
     * @returns {Promise<boolean>}
     */
    async isLoggedIn() {
        const user = await this.getCurrentUser();
        return user !== null;
    },

    /**
     * 检查是否是管理员
     * @returns {boolean}
     */
    isAdmin() {
        return this.currentUser && this.currentUser.role === 'admin';
    },

    /**
     * 获取认证令牌 (用于 WebSocket)
     * @returns {string|null}
     */
    getToken() {
        // 从 cookie 中获取 token (由服务器设置的 HttpOnly cookie)
        // 注意: HttpOnly cookie 无法通过 JS 访问，这里返回 null
        // WebSocket 连接会自动携带 cookies
        return null;
    },

    /**
     * 要求登录 (如果未登录则跳转到登录页面)
     * @returns {Promise<object|null>}
     */
    async requireAuth() {
        const user = await this.getCurrentUser();
        if (!user) {
            window.location.href = '/static/login.html';
            return null;
        }
        return user;
    },

    /**
     * 获取用户显示名称
     * @returns {string}
     */
    getDisplayName() {
        if (this.currentUser) {
            return this.currentUser.display_name || this.currentUser.username;
        }
        return '用户';
    }
};

// 导出模块
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Auth;
}
