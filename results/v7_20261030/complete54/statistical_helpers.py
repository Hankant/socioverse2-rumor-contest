def holm(p):
    p=np.array(p,float);o=np.argsort(p);v=np.minimum(1,np.maximum.accumulate((len(p)-np.arange(len(p)))*p[o]));z=np.empty(len(p));z[o]=v;return z

def fit(data,y,formula):
    Xdf=patsy.dmatrix(formula,data,return_type='dataframe');X=Xdf.to_numpy();n,p=X.shape
    assert np.linalg.matrix_rank(X)==p and n>p
    pinv=np.linalg.pinv(X);bread=pinv@pinv.T;b=pinv@y;res=y-X@b;h=np.einsum('ij,ji->i',X,pinv)
    V=(pinv*(res/(1-h))**2)@pinv.T;Vc=bread*(res@res/(n-p))
    checked=sm.OLS(y,X).fit().get_robustcov_results(cov_type='HC3',use_t=True)
    assert np.allclose(b,checked.params,atol=1e-11) and np.allclose(V,checked.cov_params(),atol=1e-10)
    G=np.asarray(patsy.build_design_matrices([Xdf.design_info],grid)[0])
    return dict(X=X,b=b,res=res,h=h,pinv=pinv,bread=bread,V=V,Vc=Vc,df=n-p,n=n,p=p,G=G,info=Xdf.design_info,
        r2=float(1-res@res/np.sum((y-y.mean())**2)),checked=checked)

def ft(m,R,robust=True):
    R=np.atleast_2d(R);v=R@(m['V'] if robust else m['Vc'])@R.T;z=R@m['b'];q=len(R)
    F=float(z@np.linalg.solve(v,z)/q)
    check=m['checked'].f_test(R,cov_p=m['V'] if robust else m['Vc'])
    assert abs(float(check.fvalue)-F)<1e-7
    return dict(F=F,df_num=q,df_den=m['df'],p=float(stats.f.sf(F,q,m['df'])))

def ct(m,L):
    est=float(L@m['b']);se=float(np.sqrt(L@m['V']@L));t=est/se;p=float(2*stats.t.sf(abs(t),m['df']))
    ci=stats.t.ppf(.975,m['df'])*se;sim=stats.t.ppf(1-.05/(2*7),m['df'])*se
    return dict(difference=est,se=se,t=t,df=m['df'],p=p,ci_low=est-ci,ci_high=est+ci,
        simultaneous_low=est-sim,simultaneous_high=est+sim)

def margins(m,factor):return [m['G'][grid[factor].eq(l)].mean(axis=0) for l in LEVELS[factor]]

def restriction(m,factor):
    means=margins(m,factor);return np.array([v-means[0] for v in means[1:]])

def wild(m,R,y,B=9999,seed=20261028):
    R=np.atleast_2d(R);Bmat=m['bread'];X=m['X'];P=m['pinv'];q=len(R)
    K=Bmat@R.T@np.linalg.inv(R@Bmat@R.T)
    br=m['b']-K@(R@m['b']);fit0=X@br
    h0=m['h']-np.einsum('ij,ji->i',X@K,R@P)
    e0=(y-fit0)/np.sqrt(1-h0)
    obs=ft(m,R)['F'];A=R@P;count=0;rng=np.random.default_rng(seed)
    for first in range(0,B,500):
        nb=min(500,B-first);Y=fit0+e0*rng.choice([-1.,1.],size=(nb,m['n']))
        bs=Y@P.T;res=Y-bs@X.T;u2=(res/(1-m['h']))**2
        V=np.einsum('in,bn,jn->bij',A,u2,A);z=bs@R.T
        Fs=np.einsum('bi,bi->b',z,np.linalg.solve(V,z[...,None])[...,0])/q
        count+=int(np.sum(Fs>=obs-1e-12))
    p=(count+1)/(B+1)
    return dict(p_wild=p,wild_B=B,wild_mcse=float(np.sqrt(p*(1-p)/(B+1))))